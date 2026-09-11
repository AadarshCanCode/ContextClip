"""
plugins/word.py — Microsoft Word plugin.

Context: document title, heading, selected text, page position.
Actions: Explain, Rewrite, Insert Summary.
"""

from __future__ import annotations

from typing import List, Optional

from core.contracts import (
    ActionDescriptor, ActionResult, AppRef, Event,
    PluginContext, PluginManifest,
)
from plugins.base import IContextClipPlugin


class WordPlugin(IContextClipPlugin):

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="com.contextclip.word",
            name="Word",
            version="1.0.0",
            protocol_version=1,
            capabilities=["read.selection", "read.activeDocument", "action.insertText"],
            triggers=["word"],
            description="Integrates with Microsoft Word for document context and actions.",
        )

    def enrich(self, app: AppRef, event: Event) -> Optional[PluginContext]:
        if app.app_family != "word":
            return None

        # Extract document name from window title
        # Typical: "Document1 - Word" or "filename.docx - Word"
        title = app.window_title
        doc_name = title.replace(" - Word", "").replace(" - Microsoft Word", "").strip()

        context_data = {
            "document_name": doc_name,
            "selected_text_length": len(event.clipboard.raw_text),
            "preview": event.clipboard.preview_text[:200],
            "content_type": event.content_type,
        }

        return PluginContext(
            plugin_id=self.manifest.id,
            app_family="word",
            context_data=context_data,
            suggested_actions=["explain_selection", "rewrite_selection", "insert_summary"],
        )

    def get_actions(self, event: Event, context: Optional[PluginContext]) -> List[ActionDescriptor]:
        return [
            ActionDescriptor(
                id="explain_selection", plugin_id=self.manifest.id,
                name="Explain", description="Explain the selected text.",
                required_capabilities=["read.selection"], confidence=0.85, icon="💡",
            ),
            ActionDescriptor(
                id="rewrite_selection", plugin_id=self.manifest.id,
                name="Rewrite", description="Rewrite the selection for clarity.",
                required_capabilities=["read.selection", "action.insertText"], confidence=0.80, icon="✏️",
            ),
            ActionDescriptor(
                id="insert_summary", plugin_id=self.manifest.id,
                name="Insert Summary", description="Insert an AI-generated summary.",
                required_capabilities=["action.insertText"], confidence=0.75, icon="📋",
            ),
        ]

    def execute(self, action_id: str, event: Event, context: Optional[PluginContext]) -> ActionResult:
        messages = {
            "explain_selection": "Generating explanation...",
            "rewrite_selection": "Rewriting selection...",
            "insert_summary": "Inserting summary at cursor...",
        }
        return ActionResult(success=True, message=messages.get(action_id, f"Executing {action_id}..."))
