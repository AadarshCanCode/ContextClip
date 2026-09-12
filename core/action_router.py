"""
core/action_router.py - deterministic bubble action routing.

This ports the bubble branch's useful idea: the model can classify context,
but Python decides which actions are allowed to appear.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.context_engine import ContextResult


@dataclass(frozen=True)
class BubbleActionDefinition:
    action_id: str
    label: str
    backend_action_id: str
    description: str = ""


ACTIONS = {
    "explain": BubbleActionDefinition(
        action_id="explain",
        label="Explain",
        backend_action_id="ai.explain_clipboard",
        description="Explain the current clipboard text.",
    ),
    "summarize": BubbleActionDefinition(
        action_id="summarize",
        label="Summarize",
        backend_action_id="ai.summarize_clipboard",
        description="Summarize the current clipboard text.",
    ),
    "help_fix": BubbleActionDefinition(
        action_id="help_fix",
        label="Help fix",
        backend_action_id="ai.help_fix_clipboard",
        description="Troubleshoot copied error or code.",
    ),
    "extract_information": BubbleActionDefinition(
        action_id="extract_information",
        label="Extract info",
        backend_action_id="ai.extract_information",
        description="Extract key information from clipboard text.",
    ),
    "draft_reply": BubbleActionDefinition(
        action_id="draft_reply",
        label="Draft reply",
        backend_action_id="ai.draft_reply",
        description="Draft a reply to copied message text.",
    ),
    "open": BubbleActionDefinition(
        action_id="open",
        label="Open link",
        backend_action_id="system.open_clipboard_url",
        description="Open a copied URL in the default browser.",
    ),
    "search_references": BubbleActionDefinition(
        action_id="search_references",
        label="Search refs",
        backend_action_id="references.search_clipboard",
        description="Search references through Exa.",
    ),
    "copy_context": BubbleActionDefinition(
        action_id="copy_context",
        label="Copy context",
        backend_action_id="context.copy_markdown",
        description="Copy active ContextClip Markdown.",
    ),
    "graph_summary": BubbleActionDefinition(
        action_id="graph_summary",
        label="Graph",
        backend_action_id="graph.summary",
        description="Summarize related captured events.",
    ),
}


def get_bubble_action_ids(context: ContextResult) -> list[str]:
    """Return deterministic semantic action ids for one context result."""
    content_type = context.content_type.strip().lower()
    intent = context.intent.strip().lower()

    if intent == "debug_error" or content_type == "error":
        return ["help_fix", "explain", "search_references"]
    if intent == "respond_to_message" or content_type == "email":
        return ["summarize", "draft_reply", "copy_context"]
    if intent == "track_deadline" or content_type == "deadline":
        return ["summarize", "extract_information", "copy_context"]
    if intent == "open_resource" or content_type == "url":
        return ["open", "summarize", "search_references"]
    if content_type == "code":
        return ["explain", "help_fix", "copy_context"]
    if content_type in {"documentation", "announcement"}:
        return ["summarize", "extract_information", "copy_context"]
    return ["summarize", "explain", "copy_context"]


def get_bubble_actions(context: ContextResult) -> list[BubbleActionDefinition]:
    return [ACTIONS[action_id] for action_id in get_bubble_action_ids(context)]
