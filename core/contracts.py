"""
core/contracts.py — Canonical domain types for ContextClip.

These are the five primitives: Event, Screenshot, Reference, WorkflowEdge,
and ContextBlock. All other layers (UI, plugins, cloud) import from here
and must not define competing versions of these types.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    COPY = "copy"
    PASTE = "paste"


class PrivacyClass(str, Enum):
    PUBLIC = "public"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class PayloadType(str, Enum):
    TEXT = "text"
    HTML = "html"
    IMAGE = "image"
    FILE_LIST = "file_list"
    RICH_TEXT = "rich_text"


class PasteMode(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"


class EdgeRelation(str, Enum):
    COPIED_FROM = "copied_from"
    PASTED_INTO = "pasted_into"
    SEARCHED_FOR = "searched_for"
    DERIVED_FROM = "derived_from"
    SOLVES = "solves"
    SAME_THREAD = "same_thread"
    FOLLOWS = "follows"


class ContentType(str, Enum):
    ERROR = "error"
    CODE = "code"
    CODE_OR_CONFIG = "code_or_config"
    SQL = "sql"
    URL = "url"
    EMAIL = "email"
    EVENT_OR_DATE = "event_or_date"
    TEXT = "text"
    EMPTY = "empty"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class AppRef:
    """Identifies the application and window that was active during an event."""
    process_name: str
    app_family: str
    window_title: str
    hwnd: Optional[int] = None
    process_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_name": self.process_name,
            "app_family": self.app_family,
            "window_title": self.window_title,
            "hwnd": self.hwnd,
            "process_id": self.process_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AppRef":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ClipboardPayload:
    """Normalized clipboard content at event time."""
    payload_hash: str       # SHA-256 of normalized content
    payload_type: PayloadType
    preview_text: str       # ≤240 chars, safe for UI
    raw_text: str           # Full text (may be truncated at MAX_CLIPBOARD_CHARS)
    byte_size: int

    @staticmethod
    def compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_hash": self.payload_hash,
            "payload_type": self.payload_type.value,
            "preview_text": self.preview_text,
            "raw_text": self.raw_text,
            "byte_size": self.byte_size,
        }


@dataclass
class ScreenshotRef:
    """Lightweight reference to a captured screenshot."""
    id: str
    sha256: str
    local_path: str
    width: int
    height: int
    created_at: str
    retention_class: str = "standard"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sha256": self.sha256,
            "local_path": self.local_path,
            "width": self.width,
            "height": self.height,
            "created_at": self.created_at,
            "retention_class": self.retention_class,
        }


# ---------------------------------------------------------------------------
# Core event (immutable after creation)
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """
    Immutable event record. Corrections are modeled as annotations or
    derived events; the original must remain auditable.
    """
    id: str
    seq: int
    type: EventType
    timestamp_utc: str
    source_app: AppRef
    clipboard: ClipboardPayload
    screenshot_id: Optional[str]            # FK -> screenshots.id
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC
    confidence: float = 1.0
    destination_app: Optional[AppRef] = None
    plugin_context: Optional[Dict[str, Any]] = None
    entities: List[str] = field(default_factory=list)
    workflow_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    paste_mode: Optional[PasteMode] = None
    content_type: str = ContentType.TEXT.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "seq": self.seq,
            "type": self.type.value,
            "timestamp_utc": self.timestamp_utc,
            "source_app": self.source_app.to_dict(),
            "clipboard": self.clipboard.to_dict(),
            "screenshot_id": self.screenshot_id,
            "privacy_class": self.privacy_class.value,
            "confidence": self.confidence,
            "destination_app": self.destination_app.to_dict() if self.destination_app else None,
            "plugin_context": self.plugin_context,
            "entities": self.entities,
            "workflow_id": self.workflow_id,
            "parent_event_id": self.parent_event_id,
            "paste_mode": self.paste_mode.value if self.paste_mode else None,
            "content_type": self.content_type,
        }

    @property
    def short_id(self) -> str:
        return self.id[:8]

    @property
    def time_label(self) -> str:
        """HH:MM formatted timestamp."""
        try:
            dt = datetime.fromisoformat(self.timestamp_utc.replace("Z", "+00:00"))
            return dt.strftime("%H:%M")
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Graph edge
# ---------------------------------------------------------------------------

@dataclass
class GraphEdge:
    """Directed relationship between two events in the ReferenceGraph."""
    id: str
    from_event_id: str
    to_event_id: str
    relation: EdgeRelation
    score: float
    source: str   # "direct" | "inferred" | "plugin" | "hash_match"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_event_id": self.from_event_id,
            "to_event_id": self.to_event_id,
            "relation": self.relation.value,
            "score": self.score,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Context block (compressed 7-event window)
# ---------------------------------------------------------------------------

@dataclass
class ContextBlock:
    """
    Derived artifact produced by cloud compression of a 7-event window.
    Raw events are never deleted; this is a convenience/speed layer.
    """
    id: str
    workflow_id: str
    event_start: int        # seq of first event
    event_end: int          # seq of last event
    event_ids: List[str]
    title: str
    one_line_goal: str
    narrative: str
    important_entities: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    app_transitions: List[str] = field(default_factory=list)
    source_hashes: List[str] = field(default_factory=list)
    created_at: str = ""
    model_info: Dict[str, Any] = field(default_factory=dict)
    safety_redactions: List[str] = field(default_factory=list)
    toon_payload: str = ""
    markdown_payload: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "event_start": self.event_start,
            "event_end": self.event_end,
            "event_ids": self.event_ids,
            "title": self.title,
            "one_line_goal": self.one_line_goal,
            "narrative": self.narrative,
            "important_entities": self.important_entities,
            "decisions": self.decisions,
            "open_questions": self.open_questions,
            "app_transitions": self.app_transitions,
            "source_hashes": self.source_hashes,
            "created_at": self.created_at,
            "model_info": self.model_info,
            "safety_redactions": self.safety_redactions,
            "toon_payload": self.toon_payload,
            "markdown_payload": self.markdown_payload,
        }


# ---------------------------------------------------------------------------
# Plugin types
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    protocol_version: int
    capabilities: List[str]
    triggers: List[str]
    description: str = ""


@dataclass
class PluginContext:
    plugin_id: str
    app_family: str
    context_data: Dict[str, Any] = field(default_factory=dict)
    suggested_actions: List[str] = field(default_factory=list)


@dataclass
class ActionDescriptor:
    id: str
    plugin_id: str
    name: str
    description: str
    required_capabilities: List[str]
    confidence: float
    icon: str = "✨"


@dataclass
class ActionResult:
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
