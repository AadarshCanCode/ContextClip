"""
core/memory.py — ReferenceStack and 7-event rolling context window.

Implements spec §4 (ReferenceStack) and §5 (7-event rolling context).

Key rules:
- ReferenceStack is the ordered human-facing sequence.
- The active context window always shows the most recent 7 events.
- When the 7th event is committed, a ContextBlock is triggered (async).
- Raw events are never deleted when a block is created.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from core.contracts import ContextBlock, Event, EventType
from storage.repositories import ContextBlockRepository, EventRepository


CONTEXT_WINDOW_SIZE = 7


class ContextWindowManager:
    """
    Manages the 7-event rolling context window.

    When the window is full, calls the on_window_ready callback
    with the event list. The window then rolls forward.
    """

    def __init__(
        self,
        event_repo: EventRepository,
        block_repo: ContextBlockRepository,
        on_window_ready: Optional[Callable[[List[Event], "ContextBlock"], None]] = None,
    ) -> None:
        self._events = event_repo
        self._blocks = block_repo
        self._on_ready = on_window_ready
        self._lock = threading.RLock()
        self._pending_event_ids: List[str] = []
        self._block_counter = self._load_block_counter()

    def _load_block_counter(self) -> int:
        blocks = self._blocks.get_all()
        return len(blocks) + 1

    def push(self, event: Event) -> Optional[ContextBlock]:
        """
        Add event to the rolling window. Returns a ContextBlock if the
        window just became full (7 events), otherwise None.
        """
        with self._lock:
            self._pending_event_ids.append(event.id)

            if len(self._pending_event_ids) >= CONTEXT_WINDOW_SIZE:
                return self._close_window()
            return None

    def _close_window(self) -> ContextBlock:
        """Compress the current window into a ContextBlock."""
        event_ids = self._pending_event_ids[:]
        self._pending_event_ids = []

        events = [self._events.get_by_id(eid) for eid in event_ids]
        events = [e for e in events if e is not None]

        from cloud.compressor import compress_with_llm

        block = compress_with_llm(events, self._block_counter)
        self._block_counter += 1

        self._blocks.insert(block)
        print(f"[Memory] ContextBlock-{block.id} created for events {block.event_start}..{block.event_end}")

        if self._on_ready:
            self._on_ready(events, block)

        return block

    def get_active_events(self, max_events: int = CONTEXT_WINDOW_SIZE) -> List[Event]:
        """Return the most recent N events (the active context window)."""
        return self._events.get_last_n(max_events)

    def get_context_blocks(self, n: int = 10) -> List[ContextBlock]:
        return self._blocks.get_latest(n)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending_event_ids)


def _build_context_block(events: List[Event], block_num: int) -> ContextBlock:
    """
    Build a ContextBlock from a list of events.
    For MVP: uses deterministic heuristics. Production uses cloud model.
    """
    from cloud.toon import encode_events_toon
    from cloud.markdown_export import export_events_markdown

    if not events:
        raise ValueError("Cannot build context block from empty event list")

    app_families = []
    seen = set()
    for e in events:
        fam = e.source_app.app_family
        if fam not in seen:
            app_families.append(fam)
            seen.add(fam)
        if e.destination_app:
            dfam = e.destination_app.app_family
            if dfam not in seen:
                app_families.append(dfam)
                seen.add(dfam)

    transitions = [
        f"{app_families[i]} -> {app_families[i+1]}"
        for i in range(len(app_families) - 1)
    ] if len(app_families) > 1 else []

    # Infer goal from error/URL content types in the events
    goal = _infer_goal(events)

    # Extract entities (URLs, error codes, identifiers)
    entities = _extract_entities(events)

    # Infer open questions
    questions = _infer_questions(events, goal)

    seqs = [e.seq for e in events]
    event_start = min(seqs)
    event_end = max(seqs)

    workflow_id = events[0].workflow_id or f"w{block_num:03d}"
    block_id = f"cb_{uuid.uuid4().hex[:8]}"

    # Build narrative
    narrative = _build_narrative(events)

    toon_payload = encode_events_toon(events)
    block_num_str = f"{block_num:03d}"

    block = ContextBlock(
        id=block_id,
        workflow_id=workflow_id,
        event_start=event_start,
        event_end=event_end,
        event_ids=[e.id for e in events],
        title=f"Context Block {block_num_str}",
        one_line_goal=goal,
        narrative=narrative,
        important_entities=entities,
        decisions=[],
        open_questions=questions,
        app_transitions=transitions,
        source_hashes=[e.clipboard.payload_hash for e in events],
        created_at=datetime.now(timezone.utc).isoformat(),
        model_info={"method": "heuristic", "version": "1.0"},
        safety_redactions=[],
        toon_payload=toon_payload,
        markdown_payload="",  # filled below
    )
    block.markdown_payload = export_events_markdown(events, block)
    return block


def _infer_goal(events: List[Event]) -> str:
    for e in events:
        if e.content_type == "error":
            return f"Resolve: {e.clipboard.preview_text[:80]}"
    for e in events:
        if e.content_type == "url":
            return f"Research: {e.clipboard.preview_text[:80]}"
    if events:
        return f"Workflow across {len(set(e.source_app.app_family for e in events))} apps"
    return "Unknown goal"


def _extract_entities(events: List[Event]) -> List[str]:
    import re
    entities = []
    seen = set()
    url_re = re.compile(r"https?://\S+")
    error_re = re.compile(r"ERR_\w+|ECONNREFUSED\s+\S+|Exception:\s*\S+", re.I)
    for e in events:
        text = e.clipboard.preview_text
        for m in url_re.findall(text):
            if m not in seen:
                entities.append(m[:80])
                seen.add(m)
        for m in error_re.findall(text):
            if m not in seen:
                entities.append(m[:60])
                seen.add(m)
    return entities[:10]


def _infer_questions(events: List[Event], goal: str) -> List[str]:
    questions = []
    families = [e.source_app.app_family for e in events]
    if "browser_chrome" in families or "browser_edge" in families:
        questions.append("Was the search query resolved?")
    if "vs_code" in families or "terminal" in families:
        questions.append("Did the fix work?")
    if not questions:
        questions.append("What is the next step?")
    return questions


def _build_narrative(events: List[Event]) -> str:
    lines = []
    for i, e in enumerate(events, 1):
        verb = "copied" if e.type == EventType.COPY else "pasted"
        dest = f" into {e.destination_app.app_family}" if e.destination_app else ""
        lines.append(
            f"{i}. {e.source_app.app_family} {verb}{dest}: {e.clipboard.preview_text[:60]}"
        )
    return "\n".join(lines)
