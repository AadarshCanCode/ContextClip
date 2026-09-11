"""
plugins/terminal.py — Terminal plugin (cmd, PowerShell, Windows Terminal).

Context: shell, command, stderr/stdout tail, working dir.
Actions: Diagnose, Retry, Explain Output.
"""

from __future__ import annotations

import re
from typing import List, Optional

from core.contracts import (
    ActionDescriptor, ActionResult, AppRef, ContentType, Event,
    PluginContext, PluginManifest,
)
from plugins.base import IContextClipPlugin

_CMD_RE = re.compile(r"^(docker|git|npm|pip|python|node|curl|wget|kubectl|az|aws)\s", re.M)


class TerminalPlugin(IContextClipPlugin):

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="com.contextclip.terminal",
            name="Terminal",
            version="1.0.0",
            protocol_version=1,
            capabilities=["read.terminal", "read.selection"],
            triggers=["terminal"],
            description="Integrates with Windows Terminal, PowerShell, and cmd.",
        )

    def enrich(self, app: AppRef, event: Event) -> Optional[PluginContext]:
        if app.app_family != "terminal":
            return None

        text = event.clipboard.preview_text
        is_error = event.content_type == ContentType.ERROR.value
        is_command = bool(_CMD_RE.search(text))

        context_data = {
            "is_error": is_error,
            "is_command": is_command,
            "shell_hint": app.process_name,
            "preview": text[:300],
        }

        suggested = []
        if is_error:
            suggested.extend(["diagnose_output", "explain_error"])
        if is_command:
            suggested.extend(["explain_command", "retry_command"])

        return PluginContext(
            plugin_id=self.manifest.id,
            app_family="terminal",
            context_data=context_data,
            suggested_actions=suggested or ["explain_output"],
        )

    def get_actions(self, event: Event, context: Optional[PluginContext]) -> List[ActionDescriptor]:
        ctx = context.context_data if context else {}
        actions = []
        if ctx.get("is_error"):
            actions.append(ActionDescriptor(
                id="diagnose_output", plugin_id=self.manifest.id,
                name="Diagnose", description="Diagnose this error output.",
                required_capabilities=["read.terminal"], confidence=0.92, icon="🔍",
            ))
        actions.append(ActionDescriptor(
            id="explain_output", plugin_id=self.manifest.id,
            name="Explain Output", description="Explain what this terminal output means.",
            required_capabilities=["read.terminal"], confidence=0.85, icon="💡",
        ))
        return actions

    def execute(self, action_id: str, event: Event, context: Optional[PluginContext]) -> ActionResult:
        messages = {
            "diagnose_output": "Diagnosing terminal output...",
            "explain_output": "Generating explanation...",
            "explain_command": "Explaining command...",
            "retry_command": "Retrying last command...",
        }
        return ActionResult(success=True, message=messages.get(action_id, f"Executing {action_id}..."))
