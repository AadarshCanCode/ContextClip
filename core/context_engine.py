"""
core/context_engine.py - clipboard semantic context models and local analysis.

The bubble branch used an LLM to classify clipboard content, then routed UI
actions deterministically. This module keeps that contract in the active app
with a local fallback that never needs a network call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from core.contracts import Event
from core.privacy import classify_content, normalize_text, safe_preview


@dataclass(frozen=True)
class Entity:
    name: str
    type: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type}


@dataclass(frozen=True)
class ContextResult:
    content_type: str
    domain: str
    summary: str
    intent: str
    entities: list[Entity] = field(default_factory=list)
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "domain": self.domain,
            "summary": self.summary,
            "intent": self.intent,
            "entities": [entity.to_dict() for entity in self.entities],
            "source": self.source,
        }


def analyze_event_locally(event: Event) -> ContextResult:
    """Build a local semantic summary from one captured event."""
    return analyze_clipboard_locally(
        clipboard_text=event.clipboard.raw_text,
        application=event.source_app.app_family or event.source_app.process_name,
        window_title=event.source_app.window_title,
        source="local",
    )


def analyze_clipboard_locally(
    clipboard_text: str,
    application: str = "",
    window_title: str = "",
    source: str = "local",
) -> ContextResult:
    """Classify clipboard text with deterministic local heuristics."""
    text = normalize_text(clipboard_text)
    content_type = _canonical_content_type(classify_content(text), text)
    intent = _infer_intent(content_type, text, application, window_title)
    domain = _infer_domain(content_type, text, application, window_title)
    entities = _extract_entities(text)
    summary = _make_summary(text, content_type, entities)
    return ContextResult(
        content_type=content_type,
        domain=domain,
        summary=summary,
        intent=intent,
        entities=entities,
        source=source,
    )


def context_result_from_dict(data: dict[str, Any], fallback_text: str = "") -> ContextResult:
    """Normalize an LLM JSON object into a ContextResult."""
    fallback = analyze_clipboard_locally(fallback_text) if fallback_text else None
    entities = []
    for item in data.get("entities") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("type") or "Entity").strip()
        if name:
            entities.append(Entity(name=name, type=entity_type))

    return ContextResult(
        content_type=str(data.get("content_type") or (fallback.content_type if fallback else "text")),
        domain=str(data.get("domain") or (fallback.domain if fallback else "general")),
        summary=str(data.get("summary") or (fallback.summary if fallback else safe_preview(fallback_text, 120))),
        intent=str(data.get("intent") or (fallback.intent if fallback else "unknown_intent")),
        entities=entities or (fallback.entities if fallback else []),
        source=str(data.get("source") or "openrouter"),
    )


def _canonical_content_type(raw_type: str, text: str) -> str:
    if raw_type == "event_or_date":
        if _DEADLINE_RE.search(text):
            return "deadline"
        return "announcement"
    if raw_type == "code_or_config":
        return "code"
    if raw_type == "sql":
        return "code"
    return raw_type or "text"


def _infer_intent(content_type: str, text: str, application: str, window_title: str) -> str:
    combined = f"{text} {application} {window_title}".lower()
    if content_type == "error":
        return "debug_error"
    if content_type == "code":
        if any(word in combined for word in ("fix", "todo", "bug", "error")):
            return "modify_code"
        return "understand_code"
    if content_type == "deadline":
        return "track_deadline"
    if content_type == "email":
        return "respond_to_message"
    if content_type == "url":
        return "open_resource"
    if any(word in combined for word in ("extract", "table", "fields", "csv", "json")):
        return "extract_information"
    if any(word in combined for word in ("deadline", "due", "submit", "upload")):
        return "track_deadline"
    if any(word in combined for word in ("readme", "docs", "documentation", "guide")):
        return "learn_topic"
    return "summarize_information"


def _infer_domain(content_type: str, text: str, application: str, window_title: str) -> str:
    combined = f"{text} {application} {window_title}".lower()
    if content_type in {"code", "error"} or any(word in combined for word in ("vscode", "terminal", "github", "api")):
        return "software"
    if content_type == "email" or any(word in combined for word in ("outlook", "mail", "teams", "slack")):
        return "communication"
    if any(word in combined for word in ("student", "course", "college", "certificate", "assignment")):
        return "education"
    if any(word in combined for word in ("invoice", "payment", "bank", "stock", "finance")):
        return "finance"
    return "general"


def _make_summary(text: str, content_type: str, entities: list[Entity]) -> str:
    if not text:
        return "Empty clipboard content"
    if content_type == "error":
        return f"Copied error or failure text: {safe_preview(text, 96)}"
    if content_type == "code":
        return f"Copied code or configuration: {safe_preview(text, 96)}"
    if content_type == "url":
        return f"Copied URL: {safe_preview(text, 96)}"
    if content_type == "email":
        return f"Copied message or email text: {safe_preview(text, 96)}"
    if content_type == "deadline":
        return f"Copied deadline-related text: {safe_preview(text, 96)}"
    if entities:
        return f"Copied text mentioning {entities[0].name}: {safe_preview(text, 96)}"
    return safe_preview(text, 120) or "Copied text"


def _extract_entities(text: str) -> list[Entity]:
    entities: list[Entity] = []
    seen = set()
    for regex, entity_type in _ENTITY_PATTERNS:
        for match in regex.finditer(text):
            name = match.group(0).strip()
            key = (name.lower(), entity_type.lower())
            if name and key not in seen:
                entities.append(Entity(name=name, type=entity_type))
                seen.add(key)
    return entities[:12]


_DEADLINE_RE = re.compile(r"\b(deadline|due|submit|upload|before|by)\b", re.I)
_ENTITY_PATTERNS = [
    (re.compile(r"https?://[^\s)>\]]+", re.I), "URL"),
    (re.compile(r"\b[A-Z][A-Za-z]+(?:Error|Exception)\b"), "Error"),
    (re.compile(r"\b(ERR_[A-Z_]+|ECONNREFUSED|ETIMEDOUT|ENOENT)\b", re.I), "Error"),
    (re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b", re.I), "Date"),
    (re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", re.I), "Date"),
    (re.compile(r"\b[A-Za-z_][\w.-]+\.(?:py|js|ts|tsx|jsx|json|md|yaml|yml|txt|docx|xlsx)\b"), "File"),
]
