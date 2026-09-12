"""
cloud/clipboard_analyzer.py - OpenRouter-backed context classification.

This adapts the bubble branch's AI classification idea to the current app's
OpenRouter requirement. It never uploads restricted clipboard content.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from core.config import load_env_file
from core.context_engine import (
    ContextResult,
    analyze_clipboard_locally,
    analyze_event_locally,
    context_result_from_dict,
)
from core.contracts import Event, PrivacyClass
from cloud.openrouter import build_openrouter_client, openrouter_model


load_env_file()


SYSTEM_PROMPT = """You classify copied desktop clipboard context for ContextClip.
Return only JSON with this exact shape:
{
  "content_type": "code|error|email|deadline|announcement|url|documentation|command|data|text|unknown",
  "domain": "software|education|work|communication|finance|travel|shopping|general|unknown",
  "summary": "one concise sentence under 120 characters",
  "intent": "debug_error|understand_code|modify_code|learn_topic|track_deadline|follow_instructions|respond_to_message|summarize_information|open_resource|save_information|extract_information|compare_information|unknown_intent",
  "entities": [{"name": "string", "type": "string"}]
}

Do not invent facts. Prefer copied text over uncertain window-title clues.
You classify and summarize only; Python will choose which actions are allowed.
"""


def analyze_event_context(event: Event, screenshot_path: Optional[str] = None) -> ContextResult:
    """Analyze one captured event for bubble action routing."""
    if event.privacy_class == PrivacyClass.RESTRICTED:
        return analyze_event_locally(event)

    mode = os.environ.get("CONTEXTCLIP_BUBBLE_ANALYZER", "openrouter").strip().lower()
    if mode == "local":
        return analyze_event_locally(event)

    try:
        return analyze_clipboard_with_openrouter(
            clipboard_text=event.clipboard.raw_text,
            application=event.source_app.app_family or event.source_app.process_name,
            window_title=event.source_app.window_title,
            screenshot_path=screenshot_path,
        )
    except Exception as exc:
        print(f"[Bubble] OpenRouter analysis failed ({exc}); using local analysis.")
        return analyze_clipboard_locally(
            clipboard_text=event.clipboard.raw_text,
            application=event.source_app.app_family or event.source_app.process_name,
            window_title=event.source_app.window_title,
            source="local_fallback",
        )


def analyze_clipboard_with_openrouter(
    clipboard_text: str,
    application: str = "",
    window_title: str = "",
    screenshot_path: Optional[str] = None,
) -> ContextResult:
    """
    Classify clipboard text through OpenRouter.

    `screenshot_path` is accepted for API symmetry with the bubble prototype,
    but current analysis is text/window-title only to keep the cloud boundary
    smaller and more predictable.
    """
    del screenshot_path
    client = build_openrouter_client()
    model = openrouter_model("OPENROUTER_ANALYZER_MODEL")
    prompt = f"""Copied content:
---
{clipboard_text[:4000]}
---

Application: {application or "unknown"}
Window title: {window_title or "unknown"}
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=450,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    data["source"] = "openrouter"
    return context_result_from_dict(data, fallback_text=clipboard_text)
