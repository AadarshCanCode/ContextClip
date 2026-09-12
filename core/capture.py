"""
core/capture.py — Clipboard listener, window context, and screenshot capture.

Design:
- ClipboardListener uses pynput to detect Ctrl+C / Ctrl+V gestures.
- WindowCapture reads the foreground window using Win32 APIs.
- ScreenshotCapture takes event-scoped screenshots (not continuous recording).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pyperclip

try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import win32gui
    import win32process
    _WIN32_AVAILABLE = True
except ImportError:
    win32gui = None
    win32process = None
    _WIN32_AVAILABLE = False

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    _PSUTIL_AVAILABLE = False

from pynput import keyboard

from core.config import get_int, load_env_file
from core.contracts import AppRef, ClipboardPayload, PayloadType, ScreenshotRef
from core.privacy import normalize_text, safe_preview

load_env_file()

# ---------------------------------------------------------------------------
# Configuration (overridable via env vars)
# ---------------------------------------------------------------------------

COPY_SETTLE_MS = get_int("CONTEXTCLIP_COPY_SETTLE_MS", 120)
MAX_CLIPBOARD_CHARS = get_int("CONTEXTCLIP_MAX_CHARS", 50000)
SCREENSHOT_MODE = os.environ.get("CONTEXTCLIP_SCREENSHOT_MODE", "active_window")

APP_FAMILY_MAP = {
    "code.exe": "vs_code",
    "code - insiders.exe": "vs_code",
    "winword.exe": "word",
    "powerpnt.exe": "powerpoint",
    "excel.exe": "excel",
    "outlook.exe": "outlook",
    "ms-teams.exe": "teams",
    "teams.exe": "teams",
    "chrome.exe": "browser_chrome",
    "msedge.exe": "browser_edge",
    "firefox.exe": "browser_firefox",
    "cmd.exe": "terminal",
    "powershell.exe": "terminal",
    "windowsterminal.exe": "terminal",
    "wt.exe": "terminal",
    "slack.exe": "slack",
    "notepad.exe": "notepad",
    "notepad++.exe": "notepad_plus",
}

APP_FAMILY_TITLE_MAP = {
    "visual studio code": "vs_code",
    "microsoft word": "word",
    "microsoft powerpoint": "powerpoint",
    "microsoft excel": "excel",
    "microsoft outlook": "outlook",
    "microsoft teams": "teams",
    "google chrome": "browser_chrome",
    "microsoft edge": "browser_edge",
    "firefox": "browser_firefox",
    "slack": "slack",
}


# ---------------------------------------------------------------------------
# Window context
# ---------------------------------------------------------------------------

def infer_app_family(process_name: str, title: str) -> str:
    p = (process_name or "").lower()
    t = (title or "").lower()
    if p in APP_FAMILY_MAP:
        return APP_FAMILY_MAP[p]
    for keyword, family in APP_FAMILY_TITLE_MAP.items():
        if keyword in t:
            return family
    if "firefox" in p:
        return "browser_firefox"
    return "unknown"


def get_foreground_window() -> AppRef:
    """Snapshot the active Windows window at call time."""
    if not _WIN32_AVAILABLE:
        return AppRef(process_name="", app_family="unknown", window_title="")

    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or ""
        process_id: Optional[int] = None
        process_name = ""

        if win32process is not None:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)

        if process_id and _PSUTIL_AVAILABLE:
            try:
                process_name = psutil.Process(process_id).name()
            except Exception:
                process_name = ""

        return AppRef(
            process_name=process_name,
            app_family=infer_app_family(process_name, title),
            window_title=title,
            hwnd=hwnd,
            process_id=process_id,
        )
    except Exception:
        return AppRef(process_name="", app_family="unknown", window_title="")


# ---------------------------------------------------------------------------
# Clipboard reading + normalization
# ---------------------------------------------------------------------------

def read_clipboard() -> str:
    try:
        text = pyperclip.paste()
        return text if isinstance(text, str) else str(text or "")
    except Exception as exc:
        print(f"[Capture] Clipboard read failed: {exc}")
        return ""


def build_clipboard_payload(text: str) -> ClipboardPayload:
    from core.privacy import classify_content
    truncated = text[:MAX_CLIPBOARD_CHARS]
    return ClipboardPayload(
        payload_hash=ClipboardPayload.compute_hash(normalize_text(truncated)),
        payload_type=PayloadType.TEXT,
        preview_text=safe_preview(truncated),
        raw_text=truncated,
        byte_size=len(text.encode("utf-8", errors="replace")),
    )


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------

class ScreenshotCapture:
    def __init__(self, screenshot_dir: Path) -> None:
        self._dir = screenshot_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def capture(self, window: AppRef, ref_id: str) -> Optional[ScreenshotRef]:
        if not _PIL_AVAILABLE:
            return None

        try:
            image: Optional[Image.Image] = None

            if (
                SCREENSHOT_MODE == "active_window"
                and _WIN32_AVAILABLE
                and window.hwnd
            ):
                left, top, right, bottom = win32gui.GetWindowRect(window.hwnd)
                if right - left > 20 and bottom - top > 20:
                    image = ImageGrab.grab(
                        bbox=(left, top, right, bottom),
                        all_screens=True,
                    )

            if image is None:
                image = ImageGrab.grab(all_screens=True)

            path = self._dir / f"{ref_id}.png"
            image.save(path)

            # Content-address the image
            img_bytes = path.read_bytes()
            sha256 = hashlib.sha256(img_bytes).hexdigest()

            return ScreenshotRef(
                id=ref_id,
                sha256=sha256,
                local_path=str(path.resolve()),
                width=image.width,
                height=image.height,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            print(f"[Capture] Screenshot failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Clipboard listener (global Ctrl+C / Ctrl+V via pynput)
# ---------------------------------------------------------------------------

class ClipboardListener:
    """
    Monitors global keyboard for Ctrl+C / Ctrl+V gestures and fires
    callbacks for copy and paste events.
    """

    def __init__(
        self,
        on_copy: Callable[[], None],
        on_paste: Callable[[], None],
    ) -> None:
        self._on_copy = on_copy
        self._on_paste = on_paste
        self._ctrl_down = False
        self._listener: Optional[keyboard.Listener] = None

    def _on_press(self, key) -> None:
        try:
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self._ctrl_down = True
                return
            if not self._ctrl_down:
                return
            if hasattr(key, "char") and key.char:
                char = key.char.lower()
                if char == "c":
                    threading.Thread(target=self._on_copy, daemon=True).start()
                elif char == "v":
                    threading.Thread(target=self._on_paste, daemon=True).start()
        except Exception as exc:
            print(f"[Listener] Key handler error: {exc}")

    def _on_release(self, key) -> None:
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._ctrl_down = False

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        print("[Listener] Global Ctrl+C / Ctrl+V monitoring active.")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
