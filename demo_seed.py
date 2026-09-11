"""
demo_seed.py — Injects the Golden Demo Scenario (spec §16) into the agent.

The 7-event demo scenario:
  1. VS Code   COPY  → ERR_CONNECTION_REFUSED 10.0.0.42:8080
  2. Browser   PASTE → search the error
  3. Browser   COPY  → documentation snippet
  4. Word      PASTE → paste into troubleshooting doc
  5. Word      COPY  → docker command from doc
  6. VS Code   PASTE → paste command into terminal/config
  7. VS Code   COPY  → successful output
                     => triggers ContextBlock-001

This seeds the SQLite database so the dashboard shows a realistic workflow
without the user having to manually copy/paste.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.agent import ContextClipAgent

from core.contracts import (
    AppRef, ClipboardPayload, ContentType, Event, EventType,
    GraphEdge, EdgeRelation, PasteMode, PrivacyClass,
)


def _utc(offset_seconds: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _app(family: str, title: str, process: str) -> AppRef:
    return AppRef(process_name=process, app_family=family, window_title=title)


def _clipboard(text: str) -> ClipboardPayload:
    from core.privacy import safe_preview
    from core.contracts import PayloadType
    return ClipboardPayload(
        payload_hash=ClipboardPayload.compute_hash(text),
        payload_type=PayloadType.TEXT,
        preview_text=safe_preview(text),
        raw_text=text,
        byte_size=len(text.encode()),
    )


DEMO_EVENTS = [
    # 1. VS Code COPY error
    {
        "type": EventType.COPY,
        "app": _app("vs_code", "server.py - contextclip - Visual Studio Code", "code.exe"),
        "text": "ERR_CONNECTION_REFUSED 10.0.0.42:8080\nFailed to connect to local API server.",
        "content_type": ContentType.ERROR.value,
        "offset": -360,
    },
    # 2. Browser PASTE (searching the error)
    {
        "type": EventType.PASTE,
        "app": _app("browser_edge", "ERR_CONNECTION_REFUSED - Google Search - Microsoft Edge", "msedge.exe"),
        "text": "ERR_CONNECTION_REFUSED 10.0.0.42:8080\nFailed to connect to local API server.",
        "content_type": ContentType.ERROR.value,
        "offset": -300,
    },
    # 3. Browser COPY documentation snippet
    {
        "type": EventType.COPY,
        "app": _app("browser_edge", "Connection Refused: How to Fix | Docker Docs - Microsoft Edge", "msedge.exe"),
        "text": "ECONNREFUSED usually means the target port is not listening. "
                "Verify the container is running: docker ps | grep api-server "
                "Then check port binding: docker inspect api-server | grep PortBindings",
        "content_type": ContentType.TEXT.value,
        "offset": -240,
    },
    # 4. Word PASTE (into troubleshooting doc)
    {
        "type": EventType.PASTE,
        "app": _app("word", "Troubleshooting Notes.docx - Word", "winword.exe"),
        "text": "ECONNREFUSED usually means the target port is not listening. "
                "Verify the container is running: docker ps | grep api-server",
        "content_type": ContentType.TEXT.value,
        "offset": -200,
    },
    # 5. Word COPY docker command
    {
        "type": EventType.COPY,
        "app": _app("word", "Troubleshooting Notes.docx - Word", "winword.exe"),
        "text": "docker run -d --name api-server -p 8080:8080 my-api:latest",
        "content_type": ContentType.CODE.value,
        "offset": -150,
    },
    # 6. VS Code PASTE command into terminal
    {
        "type": EventType.PASTE,
        "app": _app("terminal", "PowerShell - contextclip", "powershell.exe"),
        "text": "docker run -d --name api-server -p 8080:8080 my-api:latest",
        "content_type": ContentType.CODE.value,
        "offset": -100,
    },
    # 7. VS Code COPY successful output
    {
        "type": EventType.COPY,
        "app": _app("terminal", "PowerShell - contextclip", "powershell.exe"),
        "text": "d4f2a8c3b1e9\nStatus: Running\nPort: 0.0.0.0:8080->8080/tcp\nAPI server started successfully.",
        "content_type": ContentType.TEXT.value,
        "offset": -60,
    },
]


def seed_demo_events(agent: "ContextClipAgent") -> None:
    """
    Seed the demo scenario into the agent's database.
    This simulates the Golden Demo Scenario from spec §16.
    """
    print("[Demo] Seeding 7-event Golden Demo Scenario...")

    workflow_id = f"w_demo_{uuid.uuid4().hex[:6]}"
    prev_hash: str | None = None
    prev_event_id: str | None = None
    seq_start = agent._event_repo.next_seq()

    for i, ev_data in enumerate(DEMO_EVENTS):
        event_id = f"evt_demo_{uuid.uuid4().hex[:10]}"
        cb = _clipboard(ev_data["text"])
        seq = seq_start + i

        event = Event(
            id=event_id,
            seq=seq,
            type=ev_data["type"],
            timestamp_utc=_utc(ev_data["offset"]),
            source_app=ev_data["app"],
            clipboard=cb,
            screenshot_id=None,
            privacy_class=PrivacyClass.PUBLIC,
            confidence=1.0,
            workflow_id=workflow_id,
            content_type=ev_data["content_type"],
            paste_mode=PasteMode.INFERRED if ev_data["type"] == EventType.PASTE else None,
        )

        # Link paste to previous copy via parent_event_id
        if ev_data["type"] == EventType.PASTE and prev_event_id:
            event.parent_event_id = prev_event_id

        agent._event_repo.insert(event)

        if ev_data["type"] == EventType.COPY:
            agent._graph.record_copy(event)
        else:
            agent._graph.correlate_paste(event)

        agent._memory.push(event)

        if ev_data["type"] == EventType.COPY:
            prev_event_id = event_id
            prev_hash = cb.payload_hash

        # Add explicit graph edges for the demo
        if i > 0:
            prev_events = agent._event_repo.get_recent(limit=i + 1)
            if len(prev_events) >= 2:
                prev = prev_events[-2]
                relation = (
                    EdgeRelation.PASTED_INTO
                    if ev_data["type"] == EventType.PASTE
                    else EdgeRelation.FOLLOWS
                )
                agent._graph.add_edge(
                    from_id=prev.id,
                    to_id=event.id,
                    relation=relation,
                    score=0.9,
                    source="demo",
                )

        verb = "COPY" if ev_data["type"] == EventType.COPY else "PASTE"
        print(f"  [{i+1}/7] {verb} | {ev_data['app'].app_family} | {cb.preview_text[:50]}")

    print(f"[Demo] ✓ {len(DEMO_EVENTS)} events seeded into workflow {workflow_id}")
    print("[Demo] ContextBlock will be auto-generated (window is now complete).")
