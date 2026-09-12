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
            "context.save_clipboard": self._save_clipboard_context,
            "context.find_related": self._find_related_context,
            "graph.summary": self._graph_summary,
            "references.search_clipboard": self._search_clipboard_references,
            "ai.explain_clipboard": self._ai_explain_clipboard,
            "ai.summarize_clipboard": self._ai_summarize_clipboard,
            "ai.help_fix_clipboard": self._ai_help_fix_clipboard,
            "ai.extract_information": self._ai_extract_information,
            "ai.draft_reply": self._ai_draft_reply,
            "ai.adapt_code": self._ai_adapt_code,
            "system.open_clipboard_url": self._open_clipboard_url,
            "tasks.add_clipboard": self._add_clipboard_task,
            "calendar.add_clipboard": self._add_clipboard_calendar,
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
                id="context.save_clipboard",
                name="Save copied context",
                description="Save the selected copied context as a local Markdown note and JSONL record.",
                mutates=True,
            ),
            BackendActionDescriptor(
                id="context.find_related",
                name="Find related context",
                description="Find recently captured events related to the selected copied context.",
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
                id="ai.explain_clipboard",
                name="Explain clipboard",
                description="Use OpenRouter to explain the current clipboard text.",
                requires=["clipboard_read", "OPENROUTER_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="ai.summarize_clipboard",
                name="Summarize clipboard",
                description="Use OpenRouter to summarize the current clipboard text.",
                requires=["clipboard_read", "OPENROUTER_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="ai.help_fix_clipboard",
                name="Help fix clipboard issue",
                description="Use OpenRouter to troubleshoot copied error or code text.",
                requires=["clipboard_read", "OPENROUTER_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="ai.extract_information",
                name="Extract clipboard information",
                description="Use OpenRouter to extract entities, dates, tasks, URLs, and decisions.",
                requires=["clipboard_read", "OPENROUTER_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="ai.draft_reply",
                name="Draft reply",
                description="Use OpenRouter to draft a reply to copied message text.",
                requires=["clipboard_read", "OPENROUTER_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="ai.adapt_code",
                name="Adapt copied code",
                description="Use OpenRouter to explain how copied code could fit a nearby project.",
                requires=["clipboard_read", "OPENROUTER_API_KEY", "network"],
            ),
            BackendActionDescriptor(
                id="system.open_clipboard_url",
                name="Open clipboard URL",
                description="Open a copied HTTP or HTTPS URL in the default browser.",
                requires=["clipboard_read", "default_browser"],
                mutates=True,
            ),
            BackendActionDescriptor(
                id="tasks.add_clipboard",
                name="Create task",
                description="Create a local task from the selected copied context.",
                mutates=True,
            ),
            BackendActionDescriptor(
                id="calendar.add_clipboard",
                name="Add to calendar",
                description="Create a calendar event from copied context using Google Calendar credentials, with ICS fallback.",
                requires=["credentials.json"],
                mutates=True,
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
        from core.action_connections import build_action_context
        from cloud.exa_search import search_clipboard_references

        try:
            text, _context, _event = build_action_context(self._agent, kwargs)
            result = search_clipboard_references(
                text=text,
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

    def _save_clipboard_context(self, **kwargs: Any) -> BackendActionResult:
        from core.action_connections import save_context

        try:
            data = save_context(self._agent, kwargs)
        except Exception as exc:
            return BackendActionResult(
                action_id="context.save_clipboard",
                success=False,
                message=f"Save context action unavailable: {exc}",
            )
        return BackendActionResult(
            action_id="context.save_clipboard",
            success=True,
            message="Copied context saved.",
            data=data,
        )

    def _find_related_context(self, **kwargs: Any) -> BackendActionResult:
        from core.action_connections import find_related_context

        try:
            data = find_related_context(self._agent, kwargs)
        except Exception as exc:
            return BackendActionResult(
                action_id="context.find_related",
                success=False,
                message=f"Related context unavailable: {exc}",
            )
        return BackendActionResult(
            action_id="context.find_related",
            success=True,
            message=f"Found {len(data.get('related', []))} related context item(s).",
            data=data,
        )

    def _ai_explain_clipboard(self, **kwargs: Any) -> BackendActionResult:
        return self._run_ai_clipboard_action("ai.explain_clipboard", "explain", **kwargs)

    def _ai_summarize_clipboard(self, **kwargs: Any) -> BackendActionResult:
        return self._run_ai_clipboard_action("ai.summarize_clipboard", "summarize", **kwargs)

    def _ai_help_fix_clipboard(self, **kwargs: Any) -> BackendActionResult:
        return self._run_ai_clipboard_action("ai.help_fix_clipboard", "help_fix", **kwargs)

    def _ai_extract_information(self, **kwargs: Any) -> BackendActionResult:
        return self._run_ai_clipboard_action("ai.extract_information", "extract_information", **kwargs)

    def _ai_draft_reply(self, **kwargs: Any) -> BackendActionResult:
        return self._run_ai_clipboard_action("ai.draft_reply", "draft_reply", **kwargs)

    def _ai_adapt_code(self, **kwargs: Any) -> BackendActionResult:
        return self._run_ai_clipboard_action("ai.adapt_code", "adapt_code", **kwargs)

    def _run_ai_clipboard_action(self, backend_action_id: str, action_name: str, **kwargs: Any) -> BackendActionResult:
        from cloud.clipboard_actions import run_clipboard_ai_action
        from core.action_connections import build_action_context

        try:
            text, _context, _event = build_action_context(self._agent, kwargs)
            data = run_clipboard_ai_action(action_name, text=text)
        except Exception as exc:
            return BackendActionResult(
                action_id=backend_action_id,
                success=False,
                message=f"OpenRouter action unavailable: {exc}",
            )
        return BackendActionResult(
            action_id=backend_action_id,
            success=True,
            message="OpenRouter clipboard action completed.",
            data=data,
        )

    def _open_clipboard_url(self, **kwargs: Any) -> BackendActionResult:
        from core.action_connections import open_resource

        try:
            data = open_resource(self._agent, kwargs)
        except Exception as exc:
            return BackendActionResult(
                action_id="system.open_clipboard_url",
                success=False,
                message=f"Open URL action unavailable: {exc}",
            )
        return BackendActionResult(
            action_id="system.open_clipboard_url",
            success=True,
            message="Clipboard URL opened.",
            data=data,
        )

    def _add_clipboard_task(self, **kwargs: Any) -> BackendActionResult:
        from core.action_connections import add_to_tasks

        try:
            data = add_to_tasks(self._agent, kwargs)
        except Exception as exc:
            return BackendActionResult(
                action_id="tasks.add_clipboard",
                success=False,
                message=f"Create task action unavailable: {exc}",
            )
        title = data.get("task", {}).get("title", "task")
        return BackendActionResult(
            action_id="tasks.add_clipboard",
            success=True,
            message=f"Created task: {title}",
            data=data,
        )

    def _add_clipboard_calendar(self, **kwargs: Any) -> BackendActionResult:
        from core.action_connections import add_to_calendar

        try:
            data = add_to_calendar(self._agent, kwargs)
        except Exception as exc:
            return BackendActionResult(
                action_id="calendar.add_clipboard",
                success=False,
                message=f"Calendar action unavailable: {exc}",
            )
        mode = data.get("mode", "calendar")
        return BackendActionResult(
            action_id="calendar.add_clipboard",
            success=True,
            message="Calendar event prepared." if mode == "dry_run" else "Calendar action completed.",
            data=data,
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
