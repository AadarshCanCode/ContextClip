"""
plugins/vscode.py — VS Code plugin.

Provides context and actions for VS Code events (spec §10.2).
Context: file, language, diagnostics, selected code, terminal tail.
Actions: Diagnose, Explain, Generate Patch.
"""

from __future__ import annotations

from typing import List, Optional

from core.contracts import (
    ActionDescriptor, ActionResult, AppRef, ContentType, Event,
    PluginContext, PluginManifest,
)
from plugins.base import IContextClipPlugin


class VSCodePlugin(IContextClipPlugin):

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="com.contextclip.vscode",
            name="VS Code",
            version="1.0.0",
            protocol_version=1,
            capabilities=[
                "read.selection",
                "read.activeDocument",
                "read.diagnostics",
                "read.terminal",
                "action.openFile",
                "action.insertText",
            ],
            triggers=["vs_code"],
            description="Integrates with Visual Studio Code for code context and actions.",
        )

    def enrich(self, app: AppRef, event: Event) -> Optional[PluginContext]:
        if app.app_family != "vs_code":
            return None

        # Parse window title for file info: "filename.py - path - Visual Studio Code"
        parts = app.window_title.split(" - ")
        filename = parts[0].strip() if parts else ""
        # Infer language from filename extension
        language = "unknown"
        if "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
            lang_map = {
                "py": "python", "js": "javascript", "ts": "typescript",
                "rs": "rust", "go": "go", "java": "java", "cs": "csharp",
                "cpp": "cpp", "c": "c", "rb": "ruby", "sh": "shell",
                "json": "json", "yaml": "yaml", "yml": "yaml", "md": "markdown",
            }
            language = lang_map.get(ext, ext)

        context_data = {
            "filename": filename,
            "language": language,
            "is_error": event.content_type == ContentType.ERROR.value,
            "is_code": event.content_type in (ContentType.CODE.value, ContentType.CODE_OR_CONFIG.value),
            "preview": event.clipboard.preview_text[:200],
        }

        return PluginContext(
            plugin_id=self.manifest.id,
            app_family="vs_code",
            context_data=context_data,
            suggested_actions=self._suggest_actions(event, context_data),
        )

    def _suggest_actions(self, event: Event, ctx: dict) -> List[str]:
        actions = []
        if ctx.get("is_error"):
            actions.extend(["diagnose_error", "explain_error", "generate_fix"])
        elif ctx.get("is_code"):
            actions.extend(["explain_code", "generate_tests", "refactor"])
        else:
            actions.append("explain_selection")
        return actions

    def get_actions(self, event: Event, context: Optional[PluginContext]) -> List[ActionDescriptor]:
        ctx = context.context_data if context else {}
        actions = []

        if ctx.get("is_error"):
            actions.append(ActionDescriptor(
                id="diagnose_error", plugin_id=self.manifest.id,
                name="Diagnose Error", description="Analyze this error and suggest fixes.",
                required_capabilities=["read.diagnostics"], confidence=0.95, icon="🔍",
            ))
            actions.append(ActionDescriptor(
                id="generate_fix", plugin_id=self.manifest.id,
                name="Generate Fix", description="Generate a code fix for this error.",
                required_capabilities=["read.diagnostics", "action.insertText"], confidence=0.85, icon="🔧",
            ))

        if ctx.get("is_code"):
            actions.append(ActionDescriptor(
                id="explain_code", plugin_id=self.manifest.id,
                name="Explain Code", description="Explain what this code does.",
                required_capabilities=["read.selection"], confidence=0.90, icon="💡",
            ))

        return actions

    def execute(self, action_id: str, event: Event, context: Optional[PluginContext]) -> ActionResult:
        # Stub — real implementation would call VS Code extension via named pipe / IPC
        action_messages = {
            "diagnose_error": "Opening diagnostics panel for the copied error...",
            "generate_fix": "Generating code fix via AI assistant...",
            "explain_code": "Opening explanation in sidebar...",
        }
        msg = action_messages.get(action_id, f"Executing {action_id}...")
        return ActionResult(success=True, message=msg)
