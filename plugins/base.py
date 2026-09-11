"""
plugins/base.py — IContextClipPlugin base class and SDK contract.

Implements spec §9.5 and §10. Plugins sit on top of the core event store
through these interfaces; they must not own storage semantics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.contracts import (
    ActionDescriptor, ActionResult, AppRef, Event,
    PluginContext, PluginManifest,
)


class IContextClipPlugin(ABC):
    """Base class for all ContextClip plugins."""

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return the plugin manifest."""
        ...

    @abstractmethod
    def enrich(self, app: AppRef, event: Event) -> Optional[PluginContext]:
        """
        Enrich an event with app-specific context.
        Called after clipboard capture, before graph correlation.
        Return None if this plugin is not applicable to the event.
        """
        ...

    @abstractmethod
    def get_actions(self, event: Event, context: Optional[PluginContext]) -> List[ActionDescriptor]:
        """Return available actions for this event+context combination."""
        ...

    @abstractmethod
    def execute(self, action_id: str, event: Event, context: Optional[PluginContext]) -> ActionResult:
        """Execute a named action. Returns success/failure + message."""
        ...

    def health(self) -> dict:
        """Return health status. Override for real health checks."""
        return {"status": "ok", "plugin": self.manifest.id}

    def matches(self, app: AppRef) -> bool:
        """Check if this plugin applies to the given app."""
        return app.app_family in (self.manifest.triggers or [])
