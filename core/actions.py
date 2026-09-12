"""
core/actions.py - concrete backend action discovery and execution.

These actions are intentionally limited to capabilities that the backend can
perform today without removed UI artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class BackendActionError(RuntimeError):
    """Raised when an action id is unknown or cannot be dispatched."""


@dataclass(frozen=True)
class BackendActionDescriptor:
    id: str
    name: str
    description: str
    requires: list[str] = field(default_factory=list)
    mutates: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "requires": list(self.requires),
            "mutates": self.mutates,
        }


@dataclass
class BackendActionResult:
    action_id: str
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "success": self.success,
            "message": self.message,
            "data": self.data,
        }


class BackendActionBroker:
    """Discovers and executes concrete ContextClip backend actions."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        self._handlers: dict[str, Callable[..., BackendActionResult]] = {
            "storage.stats": self._storage_stats,
            "context.dump_llm_context": self._dump_llm_context,
            "context.export_markdown": self._export_markdown,
            "context.copy_markdown": self._copy_markdown,
            "graph.summary": self._graph_summary,
            "references.search_clipboard": self._search_clipboard_references,
            "capture.record_clipboard_copy": self._record_clipboard_copy,
            "capture.record_clipboard_paste": self._record_clipboard_paste,
        }
        self._descriptors = [
            BackendActionDescriptor(
                id="storage.stats",
                name="Read storage stats",
                description="Return event counts, latest sequence, and app-family totals.",
            ),
            BackendActionDescriptor(
                id="context.dump_llm_context",
                name="Dump LLM context",
                description="Return the active TOON payload, raw active events, stats, and recent context blocks.",
            ),
            BackendActionDescriptor(
                id="context.export_markdown",
                name="Export active context markdown",
                description="Render the active event window as Markdown without changing the OS clipboard.",
            ),
            BackendActionDescriptor(
                id="context.copy_markdown",
                name="Copy active context markdown",
                description="Render the active event window as Markdown and place it on the OS clipboard.",
                requires=["clipboard_write"],
                mutates=True,
            ),
            BackendActionDescriptor(
                id="graph.summary",
                name="Summarize reference graph",
                description="Return persisted graph edges and a compact text summary.",
            ),
            BackendActionDescriptor(
                id="references.search_clipboard",
                name="Search clipboard references",
                description="Search web references for current clipboard text through Exa.",
                requires=["clipboard_read", "EXA_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="capture.record_clipboard_copy",
                name="Record current clipboard as copy",
                description="Capture the current clipboard, active app metadata, screenshot, and local event state.",
                requires=["clipboard_read", "active_window", "screenshot"],
                mutates=True,
            ),
            BackendActionDescriptor(
                id="capture.record_clipboard_paste",
                name="Record current clipboard as paste",
                description="Capture the current clipboard as a paste event and correlate it to a prior copy when possible.",
                requires=["clipboard_read", "active_window", "screenshot"],
                mutates=True,
            ),
        ]

    def discover(self) -> list[BackendActionDescriptor]:
        return list(self._descriptors)

    def execute(self, action_id: str, **kwargs: Any) -> BackendActionResult:
        handler = self._handlers.get(action_id)
        if handler is None:
            raise BackendActionError(f"Unknown backend action: {action_id}")
        return handler(**kwargs)

    def _storage_stats(self, **_: Any) -> BackendActionResult:
        return BackendActionResult(
            action_id="storage.stats",
            success=True,
            message="Storage stats loaded.",
            data={
                "stats": self._agent.get_stats(),
                "app_families": self._agent.get_app_families(),
            },
        )

    def _dump_llm_context(self, **_: Any) -> BackendActionResult:
        payload = self._agent.dump_llm_context()
        return BackendActionResult(
            action_id="context.dump_llm_context",
            success=True,
            message="Active LLM context dumped.",
            data=payload,
        )

    def _export_markdown(self, **kwargs: Any) -> BackendActionResult:
        markdown = self._agent.export_active_context_markdown(
            n=int(kwargs.get("n") or 7),
        )
        return BackendActionResult(
            action_id="context.export_markdown",
            success=True,
            message="Active context Markdown rendered.",
            data={"markdown": markdown, "characters": len(markdown)},
        )

    def _copy_markdown(self, **kwargs: Any) -> BackendActionResult:
        markdown = self._agent.copy_active_context_markdown(
            n=int(kwargs.get("n") or 7),
        )
        return BackendActionResult(
            action_id="context.copy_markdown",
            success=True,
            message="Active context Markdown copied to the OS clipboard.",
            data={"characters": len(markdown)},
        )

    def _graph_summary(self, **_: Any) -> BackendActionResult:
        edges = self._agent.get_all_edges()
        return BackendActionResult(
            action_id="graph.summary",
            success=True,
            message="Reference graph summarized.",
            data={
                "summary": self._agent.summarize_graph(),
                "edges": [edge.to_dict() for edge in edges],
            },
        )

    def _search_clipboard_references(self, **kwargs: Any) -> BackendActionResult:
        try:
            result = self._agent.search_clipboard_references(
                search_type=kwargs.get("search_type") or "auto",
                num_results=int(kwargs.get("num_results") or 10),
                include_domains=_optional_list(kwargs.get("include_domains")),
                exclude_domains=_optional_list(kwargs.get("exclude_domains")),
                max_age_hours=kwargs.get("max_age_hours"),
            )
        except Exception as exc:
            return BackendActionResult(
                action_id="references.search_clipboard",
                success=False,
                message=f"Reference search unavailable: {exc}",
            )

        return BackendActionResult(
            action_id="references.search_clipboard",
            success=True,
            message=f"Exa returned {len(result.results)} reference result(s).",
            data=result.to_dict(),
        )

    def _record_clipboard_copy(self, **_: Any) -> BackendActionResult:
        event = self._agent.record_current_clipboard_copy()
        return _event_action_result(
            action_id="capture.record_clipboard_copy",
            event=event,
            success_message="Clipboard copy event recorded.",
            empty_message="No clipboard text was captured as a copy event.",
        )

    def _record_clipboard_paste(self, **_: Any) -> BackendActionResult:
        event = self._agent.record_current_clipboard_paste()
        return _event_action_result(
            action_id="capture.record_clipboard_paste",
            event=event,
            success_message="Clipboard paste event recorded.",
            empty_message="No clipboard text was captured as a paste event.",
        )


def _optional_list(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return list(value)


def _event_action_result(
    action_id: str,
    event: Any,
    success_message: str,
    empty_message: str,
) -> BackendActionResult:
    if event is None:
        return BackendActionResult(
            action_id=action_id,
            success=False,
            message=empty_message,
        )
    return BackendActionResult(
        action_id=action_id,
        success=True,
        message=success_message,
        data={"event": event.to_dict()},
    )
