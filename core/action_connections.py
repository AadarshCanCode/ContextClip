"""
core/action_connections.py - action glue for live ContextClip events.

This module ports the bubble branch's concrete action behavior into the
current backend architecture. Actions receive an optional event_id from the
Electron bubble and resolve it to the original copied text before doing work.
"""

from __future__ import annotations

import json
import os
import re
import uuid
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.capture import build_clipboard_payload, read_clipboard
from core.config import PROJECT_ROOT
from core.context_engine import analyze_clipboard_locally, analyze_event_locally
from core.contracts import Event, EventType
from core.privacy import normalize_text, safe_preview


URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)
FORM_HOST_MARKERS = (
    "forms.gle/",
    "docs.google.com/forms",
    "forms.office.com/",
    "typeform.com/",
    "form.jotform.com/",
    "surveymonkey.com/",
)
INTERNAL_URL_MARKERS = ("openrouter.ai/api/",)


def build_action_context(agent: Any, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], Optional[Event]]:
    """Resolve action kwargs to clipboard text, semantic context, and source event."""
    event = _resolve_event(agent, kwargs)
    supplied_context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}

    if event is not None:
        text = event.clipboard.raw_text
        analysis = analyze_event_locally(event).to_dict()
    else:
        text = normalize_text(str(kwargs.get("clipboard_text") or read_clipboard()))
        event = _find_matching_copy_event(agent, text)
        analysis = analyze_event_locally(event).to_dict() if event else analyze_clipboard_locally(text).to_dict()

    context = {
        **analysis,
        **supplied_context,
        "clipboard": text,
        "application": _event_application(event),
        "window_title": event.source_app.window_title if event else "",
        "process_id": _event_process_id(event),
        "screenshot_path": _event_screenshot_path(agent, event),
        "event_id": event.id if event else "",
    }
    return text, context, event


def open_resource(agent: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    text, context, _event = build_action_context(agent, kwargs)
    urls = _urls_from_context(text, context)
    if not urls:
        raise RuntimeError("No HTTP or HTTPS URL was found in the copied context.")

    preferred = [url for url in urls if _is_form_url(url) and not _is_internal_url(url)]
    regular = [url for url in urls if not _is_internal_url(url)]
    target = (preferred or regular or urls)[0]
    opened = webbrowser.open(target)
    return {"url": target, "opened": bool(opened), "url_count": len(urls)}


def save_context(agent: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    text, context, event = build_action_context(agent, kwargs)
    data_dir = _agent_data_dir(agent)
    saved_dir = data_dir / "saved_contexts"
    saved_dir.mkdir(parents=True, exist_ok=True)
    saved_id = f"ctx_{uuid.uuid4().hex[:12]}"
    record = {
        "id": saved_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "event_id": event.id if event else "",
        "title": _task_title(text, context),
        "summary": context.get("summary", ""),
        "application": context.get("application", ""),
        "content_type": context.get("content_type", ""),
        "intent": context.get("intent", ""),
        "preview": safe_preview(text, 240),
    }
    _append_jsonl(saved_dir / "saved_contexts.jsonl", record)
    markdown = _saved_context_markdown(record, text, context)
    markdown_path = saved_dir / f"{saved_id}.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    return {"saved_id": saved_id, "event_id": record["event_id"], "markdown_path": str(markdown_path)}


def add_to_tasks(agent: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    text, context, event = build_action_context(agent, kwargs)
    tasks_dir = _agent_data_dir(agent) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "event_id": event.id if event else "",
        "title": _task_title(text, context),
        "due_date": _find_date(context),
        "status": "open",
        "source": context.get("application", ""),
        "url": _first_url(text, context),
        "preview": safe_preview(text, 320),
    }
    _append_jsonl(tasks_dir / "tasks.jsonl", task)
    _append_task_text(tasks_dir / "tasks.txt", task)
    return {"task": task, "tasks_file": str(tasks_dir / "tasks.txt")}


def add_to_calendar(agent: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    _text, context, event = build_action_context(agent, kwargs)
    from cloud.google_calendar import add_to_calendar as add_google_event
    from cloud.google_calendar import build_calendar_event

    event_body = build_calendar_event(context)
    if kwargs.get("dry_run"):
        return {"mode": "dry_run", "event_id": event.id if event else "", "event": event_body}

    try:
        result = add_google_event(context)
        return {"mode": "google", **result}
    except Exception as exc:
        ics_path = _write_ics(_agent_data_dir(agent) / "calendar", event_body)
        if kwargs.get("open_ics", True):
            _open_file(ics_path)
        return {
            "mode": "ics_fallback",
            "ics_path": str(ics_path),
            "event": event_body,
            "google_error": str(exc),
        }


def find_related_context(agent: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    text, context, event = build_action_context(agent, kwargs)
    words = _keywords(f"{text} {context.get('summary', '')}")
    related = []
    for candidate in reversed(_agent_recent_events(agent, 30)):
        if event is not None and candidate.id == event.id:
            continue
        score = _score_event(candidate, words, context)
        if score <= 0:
            continue
        related.append({
            "event_id": candidate.id,
            "seq": candidate.seq,
            "score": score,
            "source": candidate.source_app.app_family or candidate.source_app.process_name,
            "preview": safe_preview(candidate.clipboard.raw_text, 180),
            "timestamp_utc": candidate.timestamp_utc,
        })
    related.sort(key=lambda item: (item["score"], item["seq"]), reverse=True)
    return {"related": related[:8], "query_terms": sorted(words)[:12]}


def _resolve_event(agent: Any, kwargs: dict[str, Any]) -> Optional[Event]:
    event_id = str(kwargs.get("event_id") or "").strip()
    if not event_id:
        return None
    getter = getattr(agent, "get_event", None)
    if callable(getter):
        return getter(event_id)
    repo = getattr(agent, "_event_repo", None)
    return repo.get_by_id(event_id) if repo is not None else None


def _find_matching_copy_event(agent: Any, text: str) -> Optional[Event]:
    if not text:
        return None
    payload_hash = build_clipboard_payload(text).payload_hash
    finder = getattr(agent, "find_recent_copy_by_hash", None)
    if callable(finder):
        return finder(payload_hash)
    for event in reversed(_agent_recent_events(agent, 50)):
        if event.type == EventType.COPY and event.clipboard.payload_hash == payload_hash:
            return event
    return None


def _urls_from_context(text: str, context: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for entity in context.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if "url" in str(entity.get("type", "")).lower():
            urls.extend(URL_RE.findall(str(entity.get("name") or "")))
    urls.extend(URL_RE.findall(text))

    seen = set()
    clean = []
    for url in urls:
        normalized = url.rstrip(".,);]}'\"")
        if normalized not in seen:
            seen.add(normalized)
            clean.append(normalized)
    return clean


def _is_form_url(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in FORM_HOST_MARKERS)


def _is_internal_url(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in INTERNAL_URL_MARKERS)


def _first_url(text: str, context: dict[str, Any]) -> str:
    urls = _urls_from_context(text, context)
    return urls[0] if urls else ""


def _task_title(text: str, context: dict[str, Any]) -> str:
    normalized = normalize_text(text)
    lowered = normalized.lower()
    first_url = _first_url(normalized, context)
    if first_url and _is_form_url(first_url):
        if "attendance" in lowered:
            return "Confirm attendance by filling out the form"
        if "registration" in lowered or "register" in lowered:
            return "Complete the registration form"
        if "survey" in lowered:
            return "Complete the survey form"
        if "confirm" in lowered:
            return "Complete the confirmation form"
        return "Complete the form"

    sentence_match = re.search(
        r"\b(?:please|kindly|action required|action needed)\b[:\s-]*(.{12,140})",
        normalized,
        re.I,
    )
    if sentence_match:
        return _sentence_title(sentence_match.group(1))

    summary = str(context.get("summary") or "").strip()
    if str(context.get("intent") or "") == "track_deadline" and summary:
        return safe_preview(summary, 90)

    action_match = re.search(
        r"\b(submit|send|upload|complete|confirm|register|respond|review|fill out|fill)\b[^.!\n]{0,120}",
        normalized,
        re.I,
    )
    if action_match:
        return _sentence_title(action_match.group(0))

    if str(context.get("content_type") or "") == "email":
        return safe_preview(summary, 90) if summary else "Follow up on the email"
    return safe_preview(summary or normalized, 90) or "Follow up on copied information"


def _sentence_title(text: str) -> str:
    title = text.strip(" :-\t\r\n")
    title = re.split(r"[.!?\n]", title, maxsplit=1)[0]
    title = title[0].upper() + title[1:] if title else title
    return safe_preview(title, 90)


def _find_date(context: dict[str, Any]) -> str:
    text = normalize_text(str(context.get("clipboard") or context.get("summary") or ""))
    lowered = text.lower()
    if "tomorrow" in lowered:
        return (date.today() + timedelta(days=1)).isoformat()
    if "today" in lowered:
        return date.today().isoformat()
    for entity in context.get("entities") or []:
        if isinstance(entity, dict) and "date" in str(entity.get("type", "")).lower():
            parsed = _parse_date(str(entity.get("name") or ""))
            if parsed:
                return parsed.isoformat()
    parsed = _parse_date(text)
    return parsed.isoformat() if parsed else ""


def _parse_date(value: str) -> Optional[date]:
    try:
        from dateutil import parser as date_parser
    except ImportError:
        return None
    try:
        return date_parser.parse(value, fuzzy=True, default=datetime.now()).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _keywords(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{3,}\b", text) if word.lower() not in _STOPWORDS}


def _score_event(event: Event, words: set[str], context: dict[str, Any]) -> int:
    candidate_words = _keywords(f"{event.clipboard.raw_text} {event.source_app.app_family}")
    score = len(words & candidate_words)
    if context.get("content_type") and str(context.get("content_type")) == event.content_type:
        score += 2
    if context.get("application") and context.get("application") == event.source_app.app_family:
        score += 1
    return score


def _saved_context_markdown(record: dict[str, Any], text: str, context: dict[str, Any]) -> str:
    return "\n".join([
        f"# {record['title']}",
        "",
        f"- Saved: {record['created_at']}",
        f"- Event: {record['event_id'] or 'none'}",
        f"- Source: {record['application'] or 'desktop'}",
        f"- Type: {record['content_type'] or 'text'}",
        f"- Intent: {record['intent'] or 'unknown'}",
        "",
        "## Summary",
        str(context.get("summary") or ""),
        "",
        "## Copied Text",
        text,
        "",
    ])


def _write_ics(directory: Path, event_body: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    uid = f"contextclip-{uuid.uuid4().hex}@contextclip.local"
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    summary = _ics_escape(str(event_body.get("summary") or "ContextClip event"))
    description = _ics_escape(str(event_body.get("description") or ""))
    start = event_body.get("start") or {}
    end = event_body.get("end") or {}

    if start.get("dateTime"):
        dtstart = _ics_datetime(str(start["dateTime"]))
        dtend = _ics_datetime(str(end.get("dateTime") or start["dateTime"]))
    else:
        dtstart = f"VALUE=DATE:{str(start.get('date') or date.today().isoformat()).replace('-', '')}"
        dtend = f"VALUE=DATE:{str(end.get('date') or (date.today() + timedelta(days=1)).isoformat()).replace('-', '')}"

    content = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ContextClip//Desktop//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;{dtstart}" if dtstart.startswith("VALUE=") else f"DTSTART:{dtstart}",
        f"DTEND;{dtend}" if dtend.startswith("VALUE=") else f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    path = directory / f"contextclip_{uuid.uuid4().hex[:10]}.ics"
    path.write_text(content, encoding="utf-8", newline="")
    return path


def _ics_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now() + timedelta(hours=1)
    return parsed.strftime("%Y%m%dT%H%M%S")


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _open_file(path: Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except AttributeError:
        webbrowser.open(path.as_uri())


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _append_task_text(path: Path, task: dict[str, Any]) -> None:
    due = f" due {task['due_date']}" if task.get("due_date") else ""
    url = f" ({task['url']})" if task.get("url") else ""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- [ ] {task['title']}{due}{url}\n")


def _agent_data_dir(agent: Any) -> Path:
    data_dir = getattr(agent, "_data_dir", None)
    return Path(data_dir) if data_dir else Path(os.environ.get("CONTEXTCLIP_DATA_DIR", PROJECT_ROOT / "contextclip_data"))


def _event_application(event: Optional[Event]) -> str:
    if event is None:
        return ""
    return event.source_app.app_family or event.source_app.process_name


def _event_process_id(event: Optional[Event]) -> str:
    if event is None or not isinstance(event.plugin_context, dict):
        return ""
    capture = event.plugin_context.get("capture")
    if isinstance(capture, dict) and capture.get("process_id"):
        return str(capture["process_id"])
    return ""


def _event_screenshot_path(agent: Any, event: Optional[Event]) -> str:
    if event is None or not event.screenshot_id:
        return ""
    getter = getattr(agent, "get_screenshot_path", None)
    if callable(getter):
        return str(getter(event.screenshot_id) or "")
    return ""


def _agent_recent_events(agent: Any, limit: int) -> list[Event]:
    getter = getattr(agent, "get_recent_events", None)
    if not callable(getter):
        return []
    return list(getter(limit))


_STOPWORDS = {
    "about",
    "after",
    "also",
    "from",
    "have",
    "into",
    "that",
    "this",
    "with",
    "your",
    "will",
    "would",
    "there",
    "their",
    "please",
}
