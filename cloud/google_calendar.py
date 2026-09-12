"""
cloud/google_calendar.py - Google Calendar integration for copied context.

This keeps calendar writes behind an explicit action. Credentials are loaded
from .env-configured paths first, then from the local credential files used by
the bubble branch checkout.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

from core.config import PROJECT_ROOT, get_str, load_env_file
from core.privacy import normalize_text, safe_preview


load_env_file()

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DEFAULT_TIMEZONE = "Asia/Kolkata"


class GoogleCalendarError(RuntimeError):
    """Raised when a Google Calendar action cannot be completed."""


def google_calendar_status() -> dict[str, Any]:
    """Return non-secret credential availability for settings/status screens."""
    credential_path = _first_existing_path(_credential_candidates())
    token_path = _first_existing_path(_token_candidates())
    return {
        "configured": credential_path is not None,
        "credential_file": credential_path.name if credential_path else "",
        "token_found": token_path is not None,
        "token_file": token_path.name if token_path else "",
        "timezone": _timezone_name(),
    }


def build_calendar_event(context: dict[str, Any]) -> dict[str, Any]:
    """Build a Google Calendar event body from ContextClip semantic context."""
    day = _find_date(context)
    clock = _find_time(context)
    summary = _event_summary(context)
    description = _event_description(context)
    timezone_name = _timezone_name()

    if clock is None:
        return {
            "summary": summary,
            "description": description,
            "start": {"date": day.isoformat()},
            "end": {"date": (day + timedelta(days=1)).isoformat()},
        }

    start = datetime.combine(day, clock)
    end = start + timedelta(hours=1)
    return {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": end.isoformat(), "timeZone": timezone_name},
    }


def add_to_calendar(context: dict[str, Any]) -> dict[str, Any]:
    """Create a Google Calendar event from copied context."""
    creds = _load_credentials()
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GoogleCalendarError("Install google-api-python-client to use Google Calendar actions.") from exc

    event_body = build_calendar_event(context)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    created = service.events().insert(calendarId="primary", body=event_body).execute()
    return {
        "provider": "google_calendar",
        "id": created.get("id", ""),
        "html_link": created.get("htmlLink", ""),
        "summary": event_body.get("summary", ""),
        "event": event_body,
    }


def _load_credentials() -> Any:
    credential_path = _first_existing_path(_credential_candidates())
    token_path = _preferred_token_path()
    if credential_path is None:
        raise GoogleCalendarError("Google Calendar credentials.json was not found.")

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise GoogleCalendarError("Install Google auth packages to use Google Calendar actions.") from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _write_token(token_path, creds)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(credential_path), SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        _write_token(token_path, creds)

    return creds


def _write_token(path: Path, creds: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")


def _find_date(context: dict[str, Any]) -> date:
    text = _context_text(context)
    today = date.today()
    lowered = text.lower()
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    if "today" in lowered:
        return today

    for entity in _entities(context):
        if "date" not in str(entity.get("type", "")).lower():
            continue
        parsed = _parse_date(str(entity.get("name", "")))
        if parsed:
            return parsed

    parsed = _parse_date(text)
    return parsed or today


def _find_time(context: dict[str, Any]) -> Optional[time]:
    text = _context_text(context)
    for entity in _entities(context):
        if "time" not in str(entity.get("type", "")).lower():
            continue
        parsed = _parse_time(str(entity.get("name", "")))
        if parsed:
            return parsed
    return _parse_time(text)


def _parse_date(value: str) -> Optional[date]:
    if not value.strip():
        return None
    try:
        from dateutil import parser as date_parser
    except ImportError as exc:
        raise GoogleCalendarError("Install python-dateutil to parse copied dates.") from exc

    try:
        return date_parser.parse(value, fuzzy=True, default=datetime.now()).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_time(value: str) -> Optional[time]:
    if not value.strip():
        return None
    try:
        from dateutil import parser as date_parser
    except ImportError as exc:
        raise GoogleCalendarError("Install python-dateutil to parse copied times.") from exc

    try:
        parsed = date_parser.parse(value, fuzzy=True, default=datetime(2000, 1, 1, 9, 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.hour == 0 and parsed.minute == 0 and not _looks_like_explicit_time(value):
        return None
    return parsed.time().replace(second=0, microsecond=0)


def _looks_like_explicit_time(value: str) -> bool:
    import re

    return bool(re.search(r"\b(?:at|@)?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b", value, re.I))


def _event_summary(context: dict[str, Any]) -> str:
    summary = str(context.get("summary") or "").strip()
    if summary:
        return safe_preview(summary, 90)
    text = _context_text(context)
    return safe_preview(text, 90) or "ContextClip event"


def _event_description(context: dict[str, Any]) -> str:
    pieces = ["Created by ContextClip from copied context."]
    source = str(context.get("application") or context.get("source_app") or "").strip()
    if source:
        pieces.append(f"Source: {source}")
    text = _context_text(context)
    if text:
        pieces.append("")
        pieces.append(safe_preview(text, 1800))
    return "\n".join(pieces)


def _context_text(context: dict[str, Any]) -> str:
    return normalize_text(str(context.get("clipboard") or context.get("text") or context.get("summary") or ""))


def _entities(context: dict[str, Any]) -> list[dict[str, Any]]:
    raw = context.get("entities") or []
    return [item for item in raw if isinstance(item, dict)]


def _timezone_name() -> str:
    return get_str("CONTEXTCLIP_CALENDAR_TIMEZONE", DEFAULT_TIMEZONE)


def _credential_candidates() -> list[Path]:
    configured = os.environ.get("CONTEXTCLIP_GOOGLE_CREDENTIALS") or os.environ.get("GOOGLE_CALENDAR_CREDENTIALS")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend([
        PROJECT_ROOT / "credentials.json",
        PROJECT_ROOT / "credential.json",
        PROJECT_ROOT / ".branch-checkouts" / "bubble" / "credentials.json",
        PROJECT_ROOT / ".branch-checkouts" / "bubble" / "credential.json",
    ])
    return candidates


def _token_candidates() -> list[Path]:
    configured = os.environ.get("CONTEXTCLIP_GOOGLE_TOKEN") or os.environ.get("GOOGLE_CALENDAR_TOKEN")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend([
        PROJECT_ROOT / "google_token.json",
        PROJECT_ROOT / ".branch-checkouts" / "bubble" / "google_token.json",
    ])
    return candidates


def _preferred_token_path() -> Path:
    existing = _first_existing_path(_token_candidates())
    if existing is not None:
        return existing
    configured = os.environ.get("CONTEXTCLIP_GOOGLE_TOKEN") or os.environ.get("GOOGLE_CALENDAR_TOKEN")
    if configured:
        return Path(configured).expanduser()
    return PROJECT_ROOT / "google_token.json"


def _first_existing_path(paths: list[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None
