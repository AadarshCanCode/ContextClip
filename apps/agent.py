"""
apps/agent.py — ContextClip Agent Service.

Orchestrates: clipboard listener -> event capture -> graph -> memory ->
context blocks -> plugin enrichment -> backend APIs.

Implements spec §7.1 (Agent process) and §15 Phase 1+2.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Resolve paths so the agent can be run from any working directory
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from core.capture import (
    ClipboardListener,
    ScreenshotCapture,
    build_clipboard_payload,
    get_cursor_position,
    get_foreground_window,
    get_text_anchor_position,
    read_clipboard,
)
from core.config import get_int, load_env_file
from core.contracts import (
    Event, EventType, GraphEdge, PasteMode, PayloadType, PrivacyClass,
)
from core.graph import ReferenceGraph
from core.memory import ContextWindowManager
from core.privacy import AppExclusionPolicy, classify_content, detect_privacy_class, normalize_text
from storage.database import initialize as init_db
from storage.repositories import (
    ContextBlockRepository,
    EventRepository,
    GraphEdgeRepository,
    ScreenshotRepository,
)

# Plugins
from plugins.vscode import VSCodePlugin
from plugins.browser import BrowserPlugin
from plugins.outlook import OutlookPlugin
from plugins.word import WordPlugin
from plugins.terminal import TerminalPlugin


load_env_file()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("CONTEXTCLIP_DATA_DIR", _HERE / "contextclip_data"))
DB_PATH = DATA_DIR / "contextclip.db"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
COPY_SETTLE_MS = get_int("CONTEXTCLIP_COPY_SETTLE_MS", 120)
CLIPBOARD_POLL_MS = get_int("CONTEXTCLIP_POLL_CLIPBOARD_MS", 250)


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_capture_position(event: Event, key: str, position: Tuple[int, int]) -> None:
    context = event.plugin_context if isinstance(event.plugin_context, dict) else {}
    capture_context = context.get("capture") if isinstance(context.get("capture"), dict) else {}
    x, y = position
    event.plugin_context = {
        **context,
        "capture": {
            **capture_context,
            key: {"x": x, "y": y},
        },
    }


class ContextClipAgent:
    """
    The core agent. Listens for Ctrl+C/Ctrl+V, captures events,
    maintains the graph, and triggers context block compression.
    """

    def __init__(
        self,
        data_dir: Path = DATA_DIR,
        on_event: Optional[Callable[[Event], None]] = None,
        on_block: Optional[Callable] = None,
    ) -> None:
        self._data_dir = data_dir
        self._on_event = on_event    # optional process-local subscriber
        self._on_block = on_block    # broadcast new context block

        # Initialize storage
        db_path = data_dir / "contextclip.db"
        init_db(db_path)

        self._event_repo = EventRepository(db_path)
        self._screenshot_repo = ScreenshotRepository(db_path)
        self._edge_repo = GraphEdgeRepository(db_path)
        self._block_repo = ContextBlockRepository(db_path)

        # Core subsystems
        self._screenshot_capture = ScreenshotCapture(data_dir / "screenshots")
        self._graph = ReferenceGraph(self._event_repo, self._edge_repo)
        self._memory = ContextWindowManager(
            self._event_repo,
            self._block_repo,
            on_window_ready=self._on_context_window_ready,
        )
        self._exclusion = AppExclusionPolicy()

        # Plugins
        self._plugins = [
            VSCodePlugin(),
            BrowserPlugin(),
            OutlookPlugin(),
            WordPlugin(),
            TerminalPlugin(),
        ]

        # State
        self._last_recorded_hash: Optional[str] = None
        self._last_seen_clipboard_hash: Optional[str] = None
        self._suppressed_clipboard_hashes: set[str] = set()
        self._last_copy_time: float = 0.0
        self._current_workflow_id: Optional[str] = self._new_workflow_id()
        self._running = False
        self._lock = threading.RLock()
        self._poll_thread: Optional[threading.Thread] = None

        # Clipboard listener
        self._listener = ClipboardListener(
            on_copy=self._handle_copy,
            on_paste=self._handle_paste,
        )

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def start(self) -> None:
        self.start_background()

        try:
            while self._running:
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stop()

    def start_background(self) -> None:
        """Start the clipboard listener without taking over the main thread."""
        if self._running:
            return
        self._running = True
        self._listener.start()
        self._start_clipboard_polling()
        print("[Agent] ContextClip Agent started.")
        print(f"[Agent] Data directory: {self._data_dir.resolve()}")
        print("[Agent] Watching global Ctrl+C / Ctrl+V. Press Ctrl+C here to stop.\n")

    def stop(self) -> None:
        self._running = False
        self._listener.stop()
        print("[Agent] Stopped.")

    def _start_clipboard_polling(self) -> None:
        """Start clipboard-change polling as a fallback to key-event capture."""
        if CLIPBOARD_POLL_MS <= 0:
            return
        current_text = read_clipboard()
        self._last_seen_clipboard_hash = self._hash_seen_clipboard(current_text)
        self._poll_thread = threading.Thread(
            target=self._poll_clipboard_loop,
            daemon=True,
        )
        self._poll_thread.start()

    def _poll_clipboard_loop(self) -> None:
        interval = max(CLIPBOARD_POLL_MS, 50) / 1000.0
        while self._running:
            time.sleep(interval)
            text = read_clipboard()
            payload_hash = self._hash_seen_clipboard(text)
            if not payload_hash:
                continue
            with self._lock:
                if payload_hash in self._suppressed_clipboard_hashes:
                    self._suppressed_clipboard_hashes.discard(payload_hash)
                    self._last_seen_clipboard_hash = payload_hash
                    continue
                if payload_hash == self._last_seen_clipboard_hash:
                    continue
                self._last_seen_clipboard_hash = payload_hash
            self._handle_copy(skip_settle=True)

    @staticmethod
    def _hash_seen_clipboard(text: str) -> Optional[str]:
        normalized = normalize_text(text)
        if not normalized:
            return None
        return build_clipboard_payload(normalized).payload_hash

    def suppress_clipboard_text(self, text: str) -> None:
        """Prevent ContextClip-owned clipboard writes from reopening the bubble."""
        payload_hash = self._hash_seen_clipboard(text)
        if not payload_hash:
            return
        with self._lock:
            self._suppressed_clipboard_hashes.add(payload_hash)
            self._last_seen_clipboard_hash = payload_hash

    # -----------------------------------------------------------------------
    # Copy handler
    # -----------------------------------------------------------------------

    def _handle_copy(self, skip_settle: bool = False) -> Optional[Event]:
        if not skip_settle:
            time.sleep(COPY_SETTLE_MS / 1000.0)

        text = read_clipboard()
        if not text.strip():
            return None

        clipboard = build_clipboard_payload(text)

        # Deduplicate rapid duplicate copies (same hash within 0.5s)
        now = time.time()
        with self._lock:
            if (
                clipboard.payload_hash == self._last_recorded_hash
                and (now - self._last_copy_time) < 0.5
            ):
                return None
            self._last_recorded_hash = clipboard.payload_hash
            self._last_copy_time = now

        window = get_foreground_window()
        anchor_position = get_text_anchor_position(window)

        # Exclusion check
        if self._exclusion.is_excluded(window.app_family, window.process_name, window.window_title):
            print(f"[Agent] Excluded app; skipping: {window.app_family}")
            return None

        # Privacy classification
        privacy = detect_privacy_class(text)
        if privacy == PrivacyClass.RESTRICTED:
            print("[Agent] Restricted content detected; event recorded locally, cloud upload blocked.")

        # Content type
        content_type = classify_content(text)

        # Screenshot
        event_id = _new_event_id()
        screenshot_ref = self._screenshot_capture.capture(window, event_id)
        if screenshot_ref:
            screenshot_ref = self._screenshot_repo.insert(screenshot_ref)

        # Build and persist event
        seq = self._event_repo.next_seq()
        event = Event(
            id=event_id,
            seq=seq,
            type=EventType.COPY,
            timestamp_utc=_utc_now(),
            source_app=window,
            clipboard=clipboard,
            screenshot_id=screenshot_ref.id if screenshot_ref else None,
            privacy_class=privacy,
            confidence=1.0,
            workflow_id=self._current_workflow_id,
            content_type=content_type,
        )

        # Plugin enrichment
        for plugin in self._plugins:
            if plugin.matches(window):
                try:
                    ctx = plugin.enrich(window, event)
                    if ctx:
                        event.plugin_context = ctx.context_data
                        break
                except Exception as exc:
                    print(f"[Agent] Plugin {plugin.manifest.id} error: {exc}")

        if anchor_position:
            _merge_capture_position(event, "anchor_position", anchor_position)

        self._event_repo.insert(event)
        self._graph.record_copy(event)
        self._memory.push(event)

        if self._on_event:
            self._on_event(event)

        self._print_copy_summary(event, screenshot_ref)
        return event

    # -----------------------------------------------------------------------
    # Paste handler
    # -----------------------------------------------------------------------

    def _handle_paste(self) -> Optional[Event]:
        window = get_foreground_window()
        cursor_position = get_cursor_position()

        # Exclusion check
        if self._exclusion.is_excluded(window.app_family, window.process_name, window.window_title):
            return None

        # Read current clipboard to correlate with the source copy
        text = read_clipboard()
        if not text.strip():
            return None

        clipboard = build_clipboard_payload(text)
        with self._lock:
            self._last_seen_clipboard_hash = clipboard.payload_hash
        content_type = classify_content(text)
        privacy = detect_privacy_class(text)

        event_id = _new_event_id()
        screenshot_ref = self._screenshot_capture.capture(window, event_id)
        if screenshot_ref:
            screenshot_ref = self._screenshot_repo.insert(screenshot_ref)

        seq = self._event_repo.next_seq()

        event = Event(
            id=event_id,
            seq=seq,
            type=EventType.PASTE,
            timestamp_utc=_utc_now(),
            source_app=window,
            destination_app=window,
            clipboard=clipboard,
            screenshot_id=screenshot_ref.id if screenshot_ref else None,
            privacy_class=privacy,
            confidence=0.9,
            paste_mode=PasteMode.INFERRED,
            workflow_id=self._current_workflow_id,
            content_type=content_type,
        )

        # Correlate with source copy event
        source_id = self._graph.find_source_for_paste(event)
        if source_id:
            event.parent_event_id = source_id

        # Plugin enrichment
        for plugin in self._plugins:
            if plugin.matches(window):
                try:
                    ctx = plugin.enrich(window, event)
                    if ctx:
                        event.plugin_context = ctx.context_data
                        break
                except Exception as exc:
                    print(f"[Agent] Plugin {plugin.manifest.id} error: {exc}")

        if cursor_position:
            _merge_capture_position(event, "cursor_position", cursor_position)

        self._event_repo.insert(event)
        self._graph.record_paste(event, source_id)
        self._memory.push(event)

        if self._on_event:
            self._on_event(event)

        print(
            f"[Agent] PASTE | {window.app_family} | "
            f"src={source_id[:8] if source_id else 'none'} | "
            f"{clipboard.preview_text[:50]}"
        )
        return event

    # -----------------------------------------------------------------------
    # Context window callback
    # -----------------------------------------------------------------------

    def _on_context_window_ready(self, events, block) -> None:
        print(f"[Agent] Context window complete -> {block.id} ({block.one_line_goal})")
        if self._on_block:
            self._on_block(block)
        # Start fresh workflow for next window
        self._current_workflow_id = self._new_workflow_id()

    # -----------------------------------------------------------------------
    # Public backend API
    # -----------------------------------------------------------------------

    def get_active_events(self, n: int = 7):
        return self._memory.get_active_events(n)

    def get_context_blocks(self, n: int = 10):
        return self._memory.get_context_blocks(n)

    def get_stats(self):
        return self._event_repo.get_stats()

    def get_app_families(self):
        return self._event_repo.get_app_families()

    def get_all_edges(self):
        return self._edge_repo.get_all()

    def get_screenshot_path(self, screenshot_id: str) -> Optional[str]:
        ref = self._screenshot_repo.get_by_id(screenshot_id)
        return ref.local_path if ref else None

    def export_active_context_markdown(self, n: int = 7) -> str:
        """Render the active event window as Markdown."""
        from cloud.markdown_export import export_events_markdown

        return export_events_markdown(self.get_active_events(n))

    def copy_active_context_markdown(self, n: int = 7) -> str:
        """Render the active event window as Markdown and copy it to the OS clipboard."""
        import pyperclip

        markdown = self.export_active_context_markdown(n)
        pyperclip.copy(markdown)
        return markdown

    def summarize_graph(self) -> str:
        """Return a compact text summary of the current reference graph."""
        return self._graph.summarize()

    def record_current_clipboard_copy(self) -> Optional[Event]:
        """Manually record the current clipboard text as a copy event."""
        return self._handle_copy()

    def record_current_clipboard_paste(self) -> Optional[Event]:
        """Manually record the current clipboard text as a paste event."""
        return self._handle_paste()

    def dump_llm_context(self) -> dict:
        """Build an LLM-ready context payload from active events."""
        from cloud.toon import encode_events_toon
        events = self.get_active_events()
        return {
            "toon": encode_events_toon(events),
            "events": [e.to_dict() for e in events],
            "stats": self.get_stats(),
            "context_blocks": [b.to_dict() for b in self.get_context_blocks(3)],
        }

    def search_clipboard_references(
        self,
        search_type: str = "auto",
        num_results: int = 10,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        max_age_hours: Optional[int] = None,
    ):
        """Search web references for the current clipboard text through Exa."""
        from cloud.exa_search import search_clipboard_references

        return search_clipboard_references(
            search_type=search_type,
            num_results=num_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            max_age_hours=max_age_hours,
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _new_workflow_id() -> str:
        return f"w_{uuid.uuid4().hex[:8]}"

    def _print_copy_summary(self, event: Event, screenshot_ref) -> None:
        print()
        print("=" * 72)
        print("[Agent] COPY captured")
        print(f"  ID        : {event.id}")
        print(f"  Seq       : {event.seq}")
        print(f"  App       : {event.source_app.app_family}")
        print(f"  Window    : {event.source_app.window_title[:60]}")
        print(f"  Type      : {event.content_type}")
        print(f"  Privacy   : {event.privacy_class.value}")
        print(f"  Preview   : {event.clipboard.preview_text[:80]}")
        print(f"  Screenshot: {screenshot_ref.local_path if screenshot_ref else 'none'}")
        print(f"  Context   : {self._memory.pending_count()}/7 events in window")
        print("=" * 72)
        print()
