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
    "add_to_calendar": BubbleActionDefinition(
        action_id="add_to_calendar",
        label="Add to Calendar",
        backend_action_id="calendar.add_clipboard",
        description="Create a calendar event from copied context.",
    ),
    "add_to_tasks": BubbleActionDefinition(
        action_id="add_to_tasks",
        label="Create Task",
        backend_action_id="tasks.add_clipboard",
        description="Create a local task from copied context.",
    ),
    "save_context": BubbleActionDefinition(
        action_id="save_context",
        label="Save Context",
        backend_action_id="context.save_clipboard",
        description="Save the copied context locally.",
    ),
    "find_related_context": BubbleActionDefinition(
        action_id="find_related_context",
        label="Related",
        backend_action_id="context.find_related",
        description="Find related recent clipboard context.",
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
        return ["help_fix", "explain", "find_related_context"]
    if intent == "track_deadline" or content_type == "deadline":
        return ["add_to_calendar", "add_to_tasks", "save_context"]
    if intent == "follow_instructions":
        return ["open", "add_to_tasks", "save_context"]
    if intent == "respond_to_message" or content_type == "email":
        if _has_action_url(context):
            return ["open", "add_to_tasks", "save_context"]
        return ["summarize", "draft_reply", "save_context"]
    if intent == "open_resource" or content_type == "url":
        return ["open", "summarize", "save_context"]
    if content_type == "code":
        return ["explain", "help_fix", "save_context"]
    if content_type == "announcement":
        if intent == "follow_instructions":
            return ["summarize", "extract_information", "save_context"]
        return ["summarize", "save_context", "extract_information"]
    if content_type == "documentation":
        return ["explain", "summarize", "save_context"]
    return ["summarize", "explain", "save_context"]


def get_bubble_actions(context: ContextResult) -> list[BubbleActionDefinition]:
    return [ACTIONS[action_id] for action_id in get_bubble_action_ids(context)]


def _has_action_url(context: ContextResult) -> bool:
    return any("url" in entity.type.lower() for entity in context.entities)
