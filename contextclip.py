"""
ContextClip - Windows workflow-context prototype
===============================================

What this prototype does
------------------------
1. Watches Ctrl+C globally.
2. After the copy completes, snapshots the active Windows screen/window.
3. Reads the clipboard text and creates a "reference node".
4. Maintains a reference stack so copied material can be chained across apps.
5. Watches Ctrl+V globally and records where a reference was pasted.
6. Stores the workflow as:
      - reference nodes
      - action/event nodes
      - directed edges between them
      - screenshots for visual context
7. Provides a compact context package for an LLM.

Typical workflow
----------------
VS Code
  Ctrl+C  -> error reference R1 + screenshot
  Ctrl+V  -> browser search/paste edge R1 -> Browser
  Ctrl+C  -> search-result/reference R2 + screenshot, linked to R1
  Ctrl+V  -> Word/Teams/etc.
  Ctrl+C  -> solution/reference R3 + screenshot, linked to R2
  Ctrl+V  -> VS Code, linked back to the active chain

The goal is NOT perfect semantic understanding in this prototype.
Instead, it reliably captures the behavioral trail that a future agent/LLM
can reason over.

Dependencies
------------
pip install pyperclip pynput pillow mss psutil pywin32

Windows notes
-------------
- Run this as a normal Windows desktop process.
- Some elevated apps may not expose their window/process metadata unless
  ContextClip itself is also run elevated.
- Browser-page DOM, Word document structure, Outlook message IDs, etc. should
  be implemented later as plugins. This prototype captures generic OS-level
  context and the clipboard workflow.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyperclip
from PIL import ImageGrab
from pynput import keyboard
import psutil

try:
    import win32gui
    import win32process
except ImportError:
    win32gui = None
    win32process = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("CONTEXTCLIP_DATA_DIR", "./contextclip_data"))
SCREENSHOT_DIR = DATA_DIR / "screenshots"
EVENT_LOG = DATA_DIR / "events.jsonl"
GRAPH_FILE = DATA_DIR / "workflow_graph.json"

SCREENSHOT_MODE = os.environ.get(
    "CONTEXTCLIP_SCREENSHOT_MODE", "active_window"
)
# Supported:
#   active_window
#   full_screen
#
# The active-window implementation uses Win32 where available. If it can't
# identify the window rectangle, it falls back to the full screen.

COPY_SETTLE_MS = 120
MAX_CLIPBOARD_CHARS = 50_000
MAX_CONTEXT_ITEMS = 25


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def classify_content(text: str) -> str:
    """Very small deterministic classifier for demo purposes."""
    s = text.strip()

    if not s:
        return "empty"

    if re.search(r"(ERR_[A-Z_]+|Exception|Traceback|connection refused|stack trace)", s, re.I):
        return "error"

    if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", s, re.I):
        return "sql"

    if re.search(r"^https?://", s, re.I):
        return "url"

    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", s, re.I):
        return "email"

    if re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", s, re.I):
        return "event_or_date"

    if re.search(r"(^|\n)\s*(def |class |function |import |from |const |let |var |public |private )", s):
        return "code"

    if len(s.splitlines()) > 3 and any(ch in s for ch in "{}[]();="):
        return "code_or_config"

    return "text"


def safe_preview(text: str, n: int = 240) -> str:
    text = normalize_text(text)
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Windows context
# ---------------------------------------------------------------------------

@dataclass
class WindowContext:
    hwnd: Optional[int] = None
    title: str = ""
    process_name: str = ""
    process_id: Optional[int] = None
    app_family: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def infer_app_family(process_name: str, title: str) -> str:
    p = (process_name or "").lower()
    t = (title or "").lower()

    if p in {"code.exe", "code - insiders.exe"} or "visual studio code" in t:
        return "vs_code"

    if p in {"winword.exe"} or "microsoft word" in t:
        return "word"

    if p in {"powerpnt.exe"} or "powerpoint" in t:
        return "powerpoint"

    if p in {"outlook.exe"} or "outlook" in t:
        return "outlook"

    if p in {"ms-teams.exe", "teams.exe"} or "microsoft teams" in t:
        return "teams"

    if p in {"chrome.exe"} or "google chrome" in t:
        return "browser_chrome"

    if p in {"msedge.exe"} or "microsoft edge" in t:
        return "browser_edge"

    if "firefox" in p:
        return "browser_firefox"

    return "unknown"


def get_foreground_window() -> WindowContext:
    if win32gui is None:
        return WindowContext(app_family="unknown")

    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or ""

        process_id = None
        process_name = ""

        if win32process is not None:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)

        if process_id:
            try:
                process_name = psutil.Process(process_id).name()
            except Exception:
                process_name = ""

        return WindowContext(
            hwnd=hwnd,
            title=title,
            process_name=process_name,
            process_id=process_id,
            app_family=infer_app_family(process_name, title),
        )
    except Exception:
        return WindowContext(app_family="unknown")


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------

def capture_screenshot(window: WindowContext, reference_id: str) -> Optional[str]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if (
            SCREENSHOT_MODE == "active_window"
            and window.hwnd
            and win32gui is not None
        ):
            left, top, right, bottom = win32gui.GetWindowRect(window.hwnd)

            # Sanity check to avoid bad/minimized rectangles.
            if right - left > 20 and bottom - top > 20:
                image = ImageGrab.grab(
                    bbox=(left, top, right, bottom),
                    all_screens=True,
                )
            else:
                image = ImageGrab.grab(all_screens=True)
        else:
            image = ImageGrab.grab(all_screens=True)

        path = SCREENSHOT_DIR / f"{reference_id}.png"
        image.save(path)
        return str(path.resolve())
    except Exception as exc:
        print(f"[ContextClip] Screenshot failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ReferenceNode:
    id: str
    created_at: str
    text: str
    content_type: str
    preview: str
    source_window: WindowContext
    screenshot_path: Optional[str]

    # The prior references that were "live" when this one was copied.
    parents: List[str] = field(default_factory=list)

    # IDs of paste/actions that consumed this reference.
    consumers: List[str] = field(default_factory=list)

    tags: List[str] = field(default_factory=list)


@dataclass
class WorkflowEvent:
    id: str
    timestamp: str
    event_type: str
    app_family: str
    window: WindowContext
    reference_id: Optional[str] = None
    target_reference_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reference stack + workflow graph
# ---------------------------------------------------------------------------

class ContextGraph:
    """
    Local append-only-ish workflow store.

    The important abstraction is:
       COPY -> reference node
       PASTE -> consumption/action event
       subsequent COPY -> linked child reference

    That turns linear clipboard history into a graph.
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.references: Dict[str, ReferenceNode] = {}
        self.events: List[WorkflowEvent] = []

        # Ordered active references. We keep a small working set rather than
        # treating clipboard history as a single variable.
        self.reference_stack: List[str] = []

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

        self._load()

    def _load(self) -> None:
        if GRAPH_FILE.exists():
            try:
                raw = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))

                for rid, item in raw.get("references", {}).items():
                    item["source_window"] = WindowContext(**item["source_window"])
                    self.references[rid] = ReferenceNode(**item)

                self.events = []
                for item in raw.get("events", []):
                    item["window"] = WindowContext(**item["window"])
                    self.events.append(WorkflowEvent(**item))

                self.reference_stack = list(raw.get("reference_stack", []))
            except Exception as exc:
                print(f"[ContextClip] Could not load graph: {exc}")

    def persist(self) -> None:
        with self.lock:
            payload = {
                "references": {
                    rid: asdict(node) for rid, node in self.references.items()
                },
                "events": [asdict(event) for event in self.events],
                "reference_stack": self.reference_stack[-MAX_CONTEXT_ITEMS:],
            }
            GRAPH_FILE.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def append_event(self, event: WorkflowEvent) -> None:
        with self.lock:
            self.events.append(event)

            with EVENT_LOG.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def add_reference(
        self,
        text: str,
        source_window: WindowContext,
        screenshot_path: Optional[str],
    ) -> ReferenceNode:
        with self.lock:
            rid = new_id("ref")

            # "Parents" are the current working references. We retain the
            # last few to form a small context chain without exploding size.
            parents = self.reference_stack[-5:].copy()

            node = ReferenceNode(
                id=rid,
                created_at=utc_now(),
                text=text[:MAX_CLIPBOARD_CHARS],
                content_type=classify_content(text),
                preview=safe_preview(text),
                source_window=source_window,
                screenshot_path=screenshot_path,
                parents=parents,
            )

            self.references[rid] = node
            self.reference_stack.append(rid)

            # Keep the working stack bounded.
            self.reference_stack = self.reference_stack[-MAX_CONTEXT_ITEMS:]

            self.persist()
            return node

    def record_paste(
        self,
        source_reference_id: Optional[str],
        target_window: WindowContext,
    ) -> WorkflowEvent:
        with self.lock:
            event = WorkflowEvent(
                id=new_id("evt"),
                timestamp=utc_now(),
                event_type="PASTE",
                app_family=target_window.app_family,
                window=target_window,
                reference_id=source_reference_id,
                payload={
                    "target_title": target_window.title,
                    "target_process": target_window.process_name,
                },
            )

            self.append_event(event)

            if source_reference_id in self.references:
                self.references[source_reference_id].consumers.append(event.id)

            self.persist()
            return event

    def record_custom_action(
        self,
        event_type: str,
        window: Optional[WindowContext] = None,
        reference_id: Optional[str] = None,
        target_reference_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> WorkflowEvent:
        window = window or get_foreground_window()

        event = WorkflowEvent(
            id=new_id("evt"),
            timestamp=utc_now(),
            event_type=event_type,
            app_family=window.app_family,
            window=window,
            reference_id=reference_id,
            target_reference_id=target_reference_id,
            payload=payload or {},
        )
        self.append_event(event)
        self.persist()
        return event

    def active_reference(self) -> Optional[ReferenceNode]:
        with self.lock:
            if not self.reference_stack:
                return None

            rid = self.reference_stack[-1]
            return self.references.get(rid)

    def build_llm_context(self, max_refs: int = 12) -> Dict[str, Any]:
        """
        Returns the material that should later be passed to an LLM.

        The LLM sees:
        - current reference
        - reference ancestors
        - where references were pasted
        - source application/window
        - screenshot paths
        - recent action history
        """
        with self.lock:
            current_ids = self.reference_stack[-max_refs:]
            refs = []

            for rid in current_ids:
                ref = self.references.get(rid)
                if not ref:
                    continue

                refs.append(
                    {
                        "id": ref.id,
                        "created_at": ref.created_at,
                        "content_type": ref.content_type,
                        "text": ref.text,
                        "preview": ref.preview,
                        "source": ref.source_window.to_dict(),
                        "screenshot_path": ref.screenshot_path,
                        "parents": ref.parents,
                        "consumers": ref.consumers,
                    }
                )

            recent_events = [
                asdict(x) for x in self.events[-30:]
            ]

            return {
                "current_reference_id": (
                    current_ids[-1] if current_ids else None
                ),
                "reference_stack": current_ids,
                "references": refs,
                "recent_events": recent_events,
                "interpretation_hint": (
                    "Treat the reference stack and event graph as workflow "
                    "context. Infer what the user is trying to accomplish "
                    "across applications rather than analyzing clipboard "
                    "items independently."
                ),
            }

    def summarize_workflow(self) -> str:
        """Human-readable demo summary."""
        with self.lock:
            lines = []
            for rid in self.reference_stack[-12:]:
                ref = self.references.get(rid)
                if not ref:
                    continue

                lines.append(
                    f"{rid}: [{ref.content_type}] "
                    f"{ref.source_window.app_family} -> "
                    f"{ref.preview}"
                )

                if ref.parents:
                    lines.append(f"    parents: {', '.join(ref.parents)}")

                if ref.consumers:
                    lines.append(f"    consumers: {', '.join(ref.consumers)}")

            return "\n".join(lines)


# ---------------------------------------------------------------------------
# Clipboard agent
# ---------------------------------------------------------------------------

class ContextClipAgent:
    def __init__(self) -> None:
        self.graph = ContextGraph()
        self.last_clipboard: Optional[str] = None
        self.last_copy_time = 0.0
        self.running = False

        # Keyboard state for global Ctrl+C / Ctrl+V.
        self.ctrl_down = False

        # Used to avoid creating duplicate copy records when another
        # application causes multiple clipboard notifications.
        self.last_recorded_text = None

    def read_clipboard(self) -> str:
        try:
            text = pyperclip.paste()
            return text if isinstance(text, str) else str(text or "")
        except Exception as exc:
            print(f"[ContextClip] Clipboard read failed: {exc}")
            return ""

    def handle_copy(self) -> None:
        # Give Windows/app time to update clipboard ownership/data.
        time.sleep(COPY_SETTLE_MS / 1000.0)

        text = self.read_clipboard()
        if not text.strip():
            return

        if text == self.last_recorded_text and (time.time() - self.last_copy_time) < 0.5:
            return

        self.last_recorded_text = text
        self.last_copy_time = time.time()

        window = get_foreground_window()

        # Snapshot the visible context at the moment of copying.
        placeholder_reference_id = new_id("ref")
        screenshot_path = capture_screenshot(window, placeholder_reference_id)

        reference = self.graph.add_reference(
            text=text,
            source_window=window,
            screenshot_path=screenshot_path,
        )

        # Rename screenshot to the real reference ID for consistency.
        if screenshot_path:
            old_path = Path(screenshot_path)
            new_path = SCREENSHOT_DIR / f"{reference.id}.png"
            try:
                old_path.rename(new_path)
                reference.screenshot_path = str(new_path.resolve())
                self.graph.persist()
            except Exception:
                pass

        event = WorkflowEvent(
            id=new_id("evt"),
            timestamp=utc_now(),
            event_type="COPY",
            app_family=window.app_family,
            window=window,
            reference_id=reference.id,
            payload={
                "content_type": reference.content_type,
                "preview": reference.preview,
                "screenshot_path": reference.screenshot_path,
            },
        )
        self.graph.append_event(event)
        self.graph.persist()

        print()
        print("=" * 78)
        print("[ContextClip] COPY captured")
        print(f"  Reference : {reference.id}")
        print(f"  App       : {window.app_family}")
        print(f"  Window    : {window.title}")
        print(f"  Type      : {reference.content_type}")
        print(f"  Text      : {reference.preview}")
        print(f"  Screenshot: {reference.screenshot_path}")
        print("=" * 78)
        print()

    def handle_paste(self) -> None:
        window = get_foreground_window()
        active = self.graph.active_reference()

        event = self.graph.record_paste(
            source_reference_id=active.id if active else None,
            target_window=window,
        )

        print(
            f"[ContextClip] PASTE "
            f"{active.id if active else '(no active ref)'} -> "
            f"{window.app_family}"
        )

    def on_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        try:
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self.ctrl_down = True
                return

            if not self.ctrl_down:
                return

            if hasattr(key, "char") and key.char:
                char = key.char.lower()

                if char == "c":
                    threading.Thread(
                        target=self.handle_copy,
                        daemon=True,
                    ).start()

                elif char == "v":
                    threading.Thread(
                        target=self.handle_paste,
                        daemon=True,
                    ).start()

                # Optional: Ctrl+Alt+H could dump the current context.
        except Exception as exc:
            print(f"[ContextClip] Key handler error: {exc}")

    def on_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.ctrl_down = False

    def start(self) -> None:
        if self.running:
            return

        self.running = True

        print("ContextClip prototype started.")
        print(f"Data directory: {DATA_DIR.resolve()}")
        print("Watching global Ctrl+C / Ctrl+V.")
        print("Press Ctrl+C in this terminal to stop.\n")

        listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release,
        )
        listener.start()

        try:
            while self.running:
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.running = False
        finally:
            listener.stop()

    def dump_context(self) -> None:
        payload = self.graph.build_llm_context()
        print(json.dumps(payload, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Demo / CLI
# ---------------------------------------------------------------------------

def print_demo_commands() -> None:
    print(
        """
ContextClip demo flow
---------------------

1. Open VS Code and copy an error:
      ERR_CONNECTION_REFUSED 10.0.0.42:8080

2. Paste it into a browser search box / Google.

3. Copy a useful search result, explanation, or code snippet.

4. Paste it into Word / Teams / another document.

5. Copy the actual fix or command.

6. Paste it back into VS Code.

ContextClip will build a graph similar to:

   [R1 VS Code error]
          |
          | pasted into
          v
   [Browser search]
          |
          | copied
          v
   [R2 solution/reference]
          |
          | pasted into
          v
   [Word / Teams]
          |
          | copied
          v
   [R3 final fix]
          |
          | pasted into
          v
   [VS Code]

The LLM context endpoint is:
    agent.graph.build_llm_context()

You can also inspect:
    agent.graph.summarize_workflow()
"""
    )


if __name__ == "__main__":
    print_demo_commands()
    agent = ContextClipAgent()
    agent.start()
