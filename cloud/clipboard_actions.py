"""
cloud/clipboard_actions.py - OpenRouter actions for current clipboard text.
"""

from __future__ import annotations

import re
import webbrowser
from typing import Any, Optional

from core.privacy import detect_privacy_class, normalize_text
from core.contracts import PrivacyClass
from cloud.openrouter import build_openrouter_client, openrouter_model


class ClipboardActionError(RuntimeError):
    """Raised when a clipboard action cannot run."""


AI_ACTION_PROMPTS = {
    "explain": "Explain the clipboard content clearly and practically.",
    "summarize": "Summarize the clipboard content in concise bullet points.",
    "help_fix": "Help troubleshoot or fix the copied error/code. Give likely causes and next checks.",
    "extract_information": "Extract key entities, dates, tasks, URLs, and decisions from the clipboard text.",
    "draft_reply": "Draft a useful reply to the copied message or email.",
    "adapt_code": "Explain how to adapt the copied code to a nearby project. State assumptions.",
}


def run_clipboard_ai_action(action_name: str, text: Optional[str] = None) -> dict[str, Any]:
    """Run one OpenRouter action against supplied or current clipboard text."""
    clipboard_text = text if text is not None else _read_clipboard()
    clipboard_text = clipboard_text.strip()
    if not clipboard_text:
        raise ClipboardActionError("Clipboard is empty; nothing to process.")
    if detect_privacy_class(clipboard_text) == PrivacyClass.RESTRICTED:
        raise ClipboardActionError("Restricted clipboard content is blocked from OpenRouter actions.")

    instruction = AI_ACTION_PROMPTS.get(action_name)
    if instruction is None:
        raise ClipboardActionError(f"Unknown clipboard AI action: {action_name}")

    client = build_openrouter_client()
    model = openrouter_model("OPENROUTER_ACTION_MODEL")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are ContextClip. Act only on the provided clipboard text. Do not invent missing context.",
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nClipboard text:\n---\n{clipboard_text[:6000]}\n---",
            },
        ],
        max_tokens=700,
    )
    output = response.choices[0].message.content or ""
    return {
        "action": action_name,
        "model": model,
        "text": output.strip(),
    }


def open_clipboard_url(text: Optional[str] = None) -> dict[str, Any]:
    """Open the current clipboard URL in the default browser."""
    clipboard_text = normalize_text(text if text is not None else _read_clipboard())
    if detect_privacy_class(clipboard_text) == PrivacyClass.RESTRICTED:
        raise ClipboardActionError("Restricted clipboard content is blocked from URL actions.")
    if not re.match(r"^https?://\S+$", clipboard_text, re.I):
        raise ClipboardActionError("Clipboard does not contain a single HTTP or HTTPS URL.")
    opened = webbrowser.open(clipboard_text)
    return {"url": clipboard_text, "opened": bool(opened)}


def _read_clipboard() -> str:
    from core.capture import read_clipboard

    return read_clipboard()
