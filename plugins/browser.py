"""
plugins/browser.py — Browser plugin (Chrome / Edge / Firefox).

Context: URL, title, selection, search query, page metadata.
Actions: Summarize, Search Related, Save Reference.
"""

from __future__ import annotations

import re
from typing import List, Optional

from core.contracts import (
    ActionDescriptor, ActionResult, AppRef, ContentType, Event,
    PluginContext, PluginManifest,
)
from plugins.base import IContextClipPlugin

_SEARCH_RE = re.compile(
    r"(google\.com/search|bing\.com/search|duckduckgo\.com/\?q|search\?q=)", re.I
)


class BrowserPlugin(IContextClipPlugin):

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="com.contextclip.browser",
            name="Browser",
            version="1.0.0",
            protocol_version=1,
            capabilities=["read.selection", "read.url", "read.title"],
            triggers=["browser_chrome", "browser_edge", "browser_firefox"],
            description="Captures browser URL, selection, and page context.",
        )

    def matches(self, app: AppRef) -> bool:
        return app.app_family in ("browser_chrome", "browser_edge", "browser_firefox")

    def enrich(self, app: AppRef, event: Event) -> Optional[PluginContext]:
        if not self.matches(app):
            return None

        text = event.clipboard.preview_text
        is_url = event.content_type == ContentType.URL.value
        is_search = bool(_SEARCH_RE.search(text))

        # Try to extract URL from clipboard if it looks like one
        url = text if is_url else ""

        context_data = {
            "url": url,
            "is_search_result": is_search,
            "is_url": is_url,
            "window_title": app.window_title,
            "preview": text[:200],
        }

        return PluginContext(
            plugin_id=self.manifest.id,
            app_family=app.app_family,
            context_data=context_data,
            suggested_actions=["summarize_page", "save_reference", "search_related"],
        )

    def get_actions(self, event: Event, context: Optional[PluginContext]) -> List[ActionDescriptor]:
        return [
            ActionDescriptor(
                id="summarize_page", plugin_id=self.manifest.id,
                name="Summarize Page", description="Summarize the current page content.",
                required_capabilities=["read.selection"], confidence=0.80, icon="📄",
            ),
            ActionDescriptor(
                id="save_reference", plugin_id=self.manifest.id,
                name="Save Reference", description="Save this page as a reference in your workflow.",
                required_capabilities=["read.url"], confidence=0.90, icon="🔖",
            ),
            ActionDescriptor(
                id="search_related", plugin_id=self.manifest.id,
                name="Search Related", description="Search for related content.",
                required_capabilities=["read.selection"], confidence=0.70, icon="🔍",
            ),
        ]

    def execute(self, action_id: str, event: Event, context: Optional[PluginContext]) -> ActionResult:
        messages = {
            "summarize_page": "Summarizing the current page...",
            "save_reference": "Reference saved to your workflow.",
            "search_related": "Opening related search in new tab...",
        }
        return ActionResult(success=True, message=messages.get(action_id, f"Executing {action_id}..."))
