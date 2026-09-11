"""
plugins/outlook.py — Outlook plugin.

Context: subject, sender, selected body, meeting details.
Actions: Add Calendar, Draft Reply, Create Task.
"""

from __future__ import annotations

import re
from typing import List, Optional

from core.contracts import (
    ActionDescriptor, ActionResult, AppRef, ContentType, Event,
    PluginContext, PluginManifest,
)
from plugins.base import IContextClipPlugin

_MEETING_RE = re.compile(
    r"(meeting|call|review|standup|interview|appointment|scheduled|zoom|teams)\s", re.I
)
_DATE_RE = re.compile(
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}:\d{2}\s*(am|pm)?)", re.I
)


class OutlookPlugin(IContextClipPlugin):

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="com.contextclip.outlook",
            name="Outlook",
            version="1.0.0",
            protocol_version=1,
            capabilities=["read.selection", "action.create", "action.open"],
            triggers=["outlook"],
            description="Integrates with Microsoft Outlook for email and calendar context.",
        )

    def enrich(self, app: AppRef, event: Event) -> Optional[PluginContext]:
        if app.app_family != "outlook":
            return None

        text = event.clipboard.preview_text
        is_meeting = bool(_MEETING_RE.search(text))
        has_date = bool(_DATE_RE.search(text))
        is_email_content = event.content_type in (
            ContentType.TEXT.value, ContentType.EVENT_OR_DATE.value
        )

        context_data = {
            "is_meeting": is_meeting,
            "has_date": has_date,
            "is_email_content": is_email_content,
            "subject_hint": app.window_title,
            "preview": text[:200],
        }

        suggested = []
        if is_meeting:
            suggested.extend(["add_to_calendar", "create_teams_meeting"])
        suggested.extend(["draft_reply", "create_task"])

        return PluginContext(
            plugin_id=self.manifest.id,
            app_family="outlook",
            context_data=context_data,
            suggested_actions=suggested,
        )

    def get_actions(self, event: Event, context: Optional[PluginContext]) -> List[ActionDescriptor]:
        ctx = context.context_data if context else {}
        actions = []

        if ctx.get("is_meeting"):
            actions.append(ActionDescriptor(
                id="add_to_calendar", plugin_id=self.manifest.id,
                name="Add to Calendar", description="Add this meeting to your calendar.",
                required_capabilities=["action.create"], confidence=0.90, icon="📅",
            ))
            actions.append(ActionDescriptor(
                id="create_teams_meeting", plugin_id=self.manifest.id,
                name="Create Teams Meeting", description="Create a Teams meeting from this context.",
                required_capabilities=["action.create", "network.outbound"], confidence=0.85, icon="💬",
            ))

        actions.append(ActionDescriptor(
            id="draft_reply", plugin_id=self.manifest.id,
            name="Draft Reply", description="Draft a reply using AI.",
            required_capabilities=["action.create"], confidence=0.80, icon="✉️",
        ))
        actions.append(ActionDescriptor(
            id="create_task", plugin_id=self.manifest.id,
            name="Create Task", description="Create a task from this content.",
            required_capabilities=["action.create"], confidence=0.75, icon="✅",
        ))

        return actions

    def execute(self, action_id: str, event: Event, context: Optional[PluginContext]) -> ActionResult:
        messages = {
            "add_to_calendar": "Opening calendar event creation...",
            "create_teams_meeting": "Creating Teams meeting link...",
            "draft_reply": "Drafting reply with AI...",
            "create_task": "Creating task in To-Do...",
        }
        return ActionResult(success=True, message=messages.get(action_id, f"Executing {action_id}..."))
