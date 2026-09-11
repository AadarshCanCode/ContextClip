"""
apps/tray.py — System tray icon for ContextClip.

Architecture:
  Main thread  → pystray icon loop (required by pystray on Windows)
  Thread 1     → ContextClipAgent (keyboard listener + clipboard capture)
  Thread 2     → Flask dashboard (on localhost:5678)

Activation: Win+Shift+C opens the dashboard in the browser.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

# Allow imports from the project root
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from apps.agent import ContextClipAgent
from apps.dashboard.app import run_dashboard, DASHBOARD_PORT

try:
    import pystray
    from pystray import MenuItem as Item
    _PYSTRAY_AVAILABLE = True
except ImportError:
    _PYSTRAY_AVAILABLE = False
    print("[Tray] pystray not installed. Run: pip install pystray")

try:
    from PIL import Image, ImageDraw
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

DATA_DIR = Path(os.environ.get("CONTEXTCLIP_DATA_DIR", _ROOT / "contextclip_data"))


# ---------------------------------------------------------------------------
# Tray icon image (drawn with Pillow — no external file needed)
# ---------------------------------------------------------------------------

def _make_icon_image(size: int = 64) -> "Image.Image":
    """Create a ContextClip tray icon programmatically."""
    if not _PIL_AVAILABLE:
        return None  # type: ignore

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded rect background — blue-purple gradient approximated as solid
    bg_color = (91, 107, 245, 255)   # #5B6BF5
    pad = 4
    draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=12, fill=bg_color)

    # Clipboard icon — white rectangle + clip
    cx, cy = size // 2, size // 2
    clip_w, clip_h = size // 3, size // 2
    left = cx - clip_w // 2
    top = cy - clip_h // 2 + 4

    # Board body
    draw.rounded_rectangle([left, top, left + clip_w, top + clip_h], radius=3, fill="white")

    # Clip at top
    clip_bar_w = clip_w // 2
    clip_left = cx - clip_bar_w // 2
    draw.rounded_rectangle(
        [clip_left, top - 5, clip_left + clip_bar_w, top + 4],
        radius=2, fill="white",
    )

    # Lines on clipboard (dark)
    line_color = bg_color
    lx = left + 4
    for i in range(3):
        y = top + 10 + i * 8
        draw.rectangle([lx, y, left + clip_w - 4, y + 2], fill=line_color)

    return img


# ---------------------------------------------------------------------------
# Tray application
# ---------------------------------------------------------------------------

class TrayApp:
    def __init__(self) -> None:
        self._agent = ContextClipAgent(data_dir=DATA_DIR)
        self._icon = None
        self._paused = False

    def _open_dashboard(self, icon=None, item=None) -> None:
        url = f"http://127.0.0.1:{DASHBOARD_PORT}"
        webbrowser.open(url)

    def _toggle_pause(self, icon=None, item=None) -> None:
        self._paused = not self._paused
        if self._paused:
            self._agent._listener.stop()
            print("[Tray] Capture paused.")
        else:
            self._agent._listener.start()
            print("[Tray] Capture resumed.")
        if self._icon:
            self._icon.update_menu()

    def _dump_context(self, icon=None, item=None) -> None:
        import json
        ctx = self._agent.dump_llm_context()
        print("\n=== LLM CONTEXT DUMP ===")
        print(json.dumps(ctx, indent=2, ensure_ascii=False))
        print("========================\n")

    def _clear_history(self, icon=None, item=None) -> None:
        # POST to the dashboard API (if running) or clear directly
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{DASHBOARD_PORT}/api/clear",
                method="POST",
            )
            urllib.request.urlopen(req, timeout=2)
            print("[Tray] History cleared.")
        except Exception:
            print("[Tray] Dashboard not running — could not clear via API.")

    def _exit(self, icon=None, item=None) -> None:
        print("[Tray] Exiting ContextClip...")
        self._agent.stop()
        if self._icon:
            self._icon.stop()

    def _build_menu(self):
        if not _PYSTRAY_AVAILABLE:
            return None

        pause_text = "Resume Capture" if self._paused else "Pause Capture"

        return (
            Item("ContextClip", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Open Dashboard", self._open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            Item(pause_text, self._toggle_pause),
            Item("Dump Context (JSON)", self._dump_context),
            Item("Clear History", self._clear_history),
            pystray.Menu.SEPARATOR,
            Item("Exit", self._exit),
        )

    def run(self) -> None:
        # Thread 1: Agent (clipboard listener)
        agent_thread = threading.Thread(
            target=self._run_agent,
            daemon=True,
            name="ContextClip-Agent",
        )
        agent_thread.start()

        # Thread 2: Flask dashboard
        dashboard_thread = threading.Thread(
            target=run_dashboard,
            args=(self._agent,),
            daemon=True,
            name="ContextClip-Dashboard",
        )
        dashboard_thread.start()

        print(f"[Tray] Dashboard: http://127.0.0.1:{DASHBOARD_PORT}")
        print("[Tray] Starting system tray icon...")

        if not _PYSTRAY_AVAILABLE or not _PIL_AVAILABLE:
            print("[Tray] pystray/Pillow not available. Running without tray icon.")
            print("[Tray] Press Ctrl+C to stop.")
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self._agent.stop()
            return

        icon_image = _make_icon_image(64)
        self._icon = pystray.Icon(
            "ContextClip",
            icon_image,
            "ContextClip",
            menu=pystray.Menu(self._build_menu),
        )

        # Auto-open dashboard on first launch
        webbrowser.open(f"http://127.0.0.1:{DASHBOARD_PORT}")

        self._icon.run()

    def _run_agent(self) -> None:
        """Run the agent without its own blocking loop (tray controls lifecycle)."""
        import time
        self._agent._running = True
        self._agent._listener.start()
        print("[Agent] ContextClip Agent started.")
        print(f"[Agent] Data directory: {self._agent._data_dir.resolve()}")
        print("[Agent] Watching global Ctrl+C / Ctrl+V.\n")
        while self._agent._running:
            time.sleep(0.25)


def main() -> None:
    """Entry point for the tray application."""
    print("=" * 60)
    print("  ContextClip v4")
    print("  Information in motion. Workflows in action.")
    print("=" * 60)
    print()
    tray = TrayApp()
    tray.run()


if __name__ == "__main__":
    main()
