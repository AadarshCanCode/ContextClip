"""
cloud/toon.py — TOON (Token-Oriented Object Notation) serializer.

TOON is used only at the LLM boundary, not for persistence.
The format is a compact, human-readable encoding of arrays of uniform objects.

Spec §5.2-5.3 format:
  typeName[count]{field1,field2,...}:
    value1,value2,...
    value1,value2,...

Reference: toonformat.dev / github.com/milanjaros/toon-format-spec
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from core.contracts import Event, EventType


# ---------------------------------------------------------------------------
# TOON encoder for events
# ---------------------------------------------------------------------------

def _short_time(ts: str) -> str:
    """Format ISO timestamp as HH:MM."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except Exception:
        return ts[:5]


def _short_app(app_family: str) -> str:
    """Compact app family name for TOON row."""
    abbrev = {
        "vs_code": "VSCode",
        "browser_chrome": "Chrome",
        "browser_edge": "Edge",
        "browser_firefox": "Firefox",
        "word": "Word",
        "powerpoint": "PPT",
        "excel": "Excel",
        "outlook": "Outlook",
        "teams": "Teams",
        "terminal": "Terminal",
        "slack": "Slack",
        "unknown": "?",
    }
    return abbrev.get(app_family, app_family[:8])


def _short_hash(h: str) -> str:
    """First 8 chars of sha256 for TOON."""
    return h[:8] if h else "00000000"


def encode_events_toon(events: List[Event]) -> str:
    """
    Encode a list of events as TOON for LLM input.

    Output format (per spec §5.3):
      window[N]{id,type,time,app,target,summary,hash}:
        e101,copy,10:02,VSCode,error.log,ECONNREFUSED...,sha256:aa
        ...
      workflow:
        id:wNN
        goal:...
        links[M]:e101->e102,...
    """
    if not events:
        return "window[0]{id,type,time,app,target,summary,hash}:"

    n = len(events)
    lines = [f"window[{n}]{{id,type,time,app,target,summary,hash}}:"]

    for e in events:
        eid = e.id[:8]
        etype = e.type.value
        etime = _short_time(e.timestamp_utc)
        eapp = _short_app(e.source_app.app_family)
        etarget = _short_app(e.destination_app.app_family) if e.destination_app else e.source_app.window_title[:15]
        esummary = e.clipboard.preview_text[:40].replace(",", ";").replace("\n", " ")
        ehash = f"sha256:{_short_hash(e.clipboard.payload_hash)}"
        lines.append(f"  {eid},{etype},{etime},{eapp},{etarget},{esummary},{ehash}")

    # Workflow block
    workflow_id = events[0].workflow_id or "w001"
    lines.append("workflow:")
    lines.append(f"  id:{workflow_id}")

    # Infer goal from content types
    goal = "unknown"
    for e in events:
        if e.content_type == "error":
            goal = f"resolve:{e.clipboard.preview_text[:30].replace(',', ';')}"
            break
    lines.append(f"  goal:{goal}")

    # Build links from adjacent events
    links = []
    for i in range(len(events) - 1):
        a = events[i].id[:8]
        b = events[i + 1].id[:8]
        links.append(f"{a}->{b}")
    if links:
        lines.append(f"  links[{len(links)}]:{','.join(links)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TOON decoder (for reading LLM output back into structured data)
# ---------------------------------------------------------------------------

def decode_toon(toon_str: str) -> Dict[str, Any]:
    """
    Parse a TOON payload back into a Python dict.
    Returns {"events": [...], "workflow": {...}}
    """
    result: Dict[str, Any] = {"events": [], "workflow": {}}
    lines = toon_str.strip().splitlines()

    headers: List[str] = []
    in_events = False
    in_workflow = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("window["):
            # Parse header: window[N]{f1,f2,...}:
            in_events = True
            in_workflow = False
            try:
                fields_part = stripped.split("{")[1].split("}")[0]
                headers = [f.strip() for f in fields_part.split(",")]
            except Exception:
                headers = ["id", "type", "time", "app", "target", "summary", "hash"]
            continue

        if stripped == "workflow:":
            in_events = False
            in_workflow = True
            continue

        if in_events and not stripped.startswith("#"):
            values = [v.strip() for v in stripped.split(",")]
            event_dict = dict(zip(headers, values))
            result["events"].append(event_dict)

        if in_workflow and ":" in stripped:
            key, _, val = stripped.partition(":")
            result["workflow"][key.strip()] = val.strip()

    return result
