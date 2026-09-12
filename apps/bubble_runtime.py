"""
apps/bubble_runtime.py - desktop bubble app runner.

Runs the existing ContextClipAgent with a Tkinter bubble UI. The agent captures
events; this runtime only decides what to show and how button clicks dispatch
through the backend action broker.
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from typing import Any, Optional, Tuple

import pyperclip

from apps.agent import ContextClipAgent
from apps.bubble import ContextBubble
from cloud.clipboard_analyzer import analyze_event_context
from core.action_router import BubbleActionDefinition, get_bubble_actions
from core.actions import BackendActionBroker, BackendActionResult
from core.contracts import Event, EventType
from core.privacy import safe_preview


class ContextClipBubbleApp:
    """Native desktop bubble experience for captured copy events."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.bubble = ContextBubble(self.root)
        self.agent = ContextClipAgent(on_event=self._on_event)
        self.broker = BackendActionBroker(self.agent)
        self.queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.running = False

    def start(self) -> None:
        self.running = True
        self.root.after(80, self._drain_queue)
        self.agent.start_background()
        print("[Bubble] Native copy bubble enabled.")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.agent.stop()
        self.bubble.hide()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _on_event(self, event: Event) -> None:
        if event.type != EventType.COPY:
            return
        self.queue.put(("event", event))

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break

            if kind == "event":
                self._show_analyzing(payload)
            elif kind == "analysis":
                event, context, anchor = payload
                self._show_analysis(event, context, anchor)
            elif kind == "action_result":
                action, result, anchor = payload
                self._show_action_result(action, result, anchor)

        if self.running:
            self.root.after(80, self._drain_queue)

    def _show_analyzing(self, event: Event) -> None:
        anchor = _anchor_from_event(event)
        self.bubble.show(
            title="Copy captured",
            subtitle=safe_preview(event.clipboard.preview_text, 88),
            detail=f"Analyzing context from {event.source_app.app_family or 'desktop'}...",
            actions=[("Working", lambda: None)],
            anchor=anchor,
        )
        threading.Thread(
            target=self._analyze_in_background,
            args=(event, anchor),
            daemon=True,
        ).start()

    def _analyze_in_background(self, event: Event, anchor: Optional[Tuple[int, int]]) -> None:
        screenshot_path = self.agent.get_screenshot_path(event.screenshot_id) if event.screenshot_id else None
        context = analyze_event_context(event, screenshot_path=screenshot_path)
        self.queue.put(("analysis", (event, context, anchor)))

    def _show_analysis(self, event: Event, context: Any, anchor: Optional[Tuple[int, int]]) -> None:
        actions = get_bubble_actions(context)
        buttons = [
            (action.label, self._action_callback(action, anchor))
            for action in actions[:3]
        ]
        relation = self._relation_for_event(event)
        source = event.source_app.app_family or event.source_app.process_name or "desktop"
        self.bubble.show(
            title=context.intent.replace("_", " "),
            subtitle=safe_preview(context.summary, 100),
            detail=f"Copied from {source} | {context.content_type} | {context.source}",
            relation=relation,
            actions=buttons,
            anchor=anchor,
        )

    def _action_callback(
        self,
        action: BubbleActionDefinition,
        anchor: Optional[Tuple[int, int]],
    ):
        return lambda: self._run_action_async(action, anchor)

    def _run_action_async(
        self,
        action: BubbleActionDefinition,
        anchor: Optional[Tuple[int, int]],
    ) -> None:
        self.bubble.show(
            title="Running action",
            subtitle=action.label,
            detail=action.description or action.backend_action_id,
            actions=[("Working", lambda: None)],
            anchor=anchor,
        )
        threading.Thread(
            target=self._run_action_in_background,
            args=(action, anchor),
            daemon=True,
        ).start()

    def _run_action_in_background(
        self,
        action: BubbleActionDefinition,
        anchor: Optional[Tuple[int, int]],
    ) -> None:
        result = self.broker.execute(action.backend_action_id)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        self.queue.put(("action_result", (action, result, anchor)))

    def _show_action_result(
        self,
        action: BubbleActionDefinition,
        result: BackendActionResult,
        anchor: Optional[Tuple[int, int]],
    ) -> None:
        text = _result_text(result)
        buttons = [("Close", self.bubble.hide)]
        if text:
            buttons.insert(0, ("Copy result", lambda: pyperclip.copy(text)))

        self.bubble.show(
            title="Action complete" if result.success else "Action unavailable",
            subtitle=safe_preview(text or result.message, 108),
            detail=f"{action.label}: {result.message}",
            actions=buttons,
            anchor=anchor,
        )

    def _relation_for_event(self, event: Event) -> Optional[str]:
        for edge in reversed(self.agent.get_all_edges()[-8:]):
            if edge.to_event_id == event.id:
                return f"Related to event {edge.from_event_id[:8]} ({edge.relation.value})"
        return None


def _anchor_from_event(event: Event) -> Optional[Tuple[int, int]]:
    context = event.plugin_context or {}
    capture = context.get("capture") if isinstance(context, dict) else None
    position = capture.get("cursor_position") if isinstance(capture, dict) else None
    if not isinstance(position, dict):
        return None
    try:
        return int(position["x"]), int(position["y"])
    except (KeyError, TypeError, ValueError):
        return None


def _result_text(result: BackendActionResult) -> str:
    data = result.data or {}
    if isinstance(data.get("text"), str):
        return data["text"]
    if isinstance(data.get("markdown"), str):
        return data["markdown"]
    if isinstance(data.get("summary"), str):
        return data["summary"]
    if isinstance(data.get("results"), list):
        titles = [item.get("title", "") for item in data["results"] if isinstance(item, dict)]
        return "\n".join(title for title in titles if title)
    if data:
        return json.dumps(data, indent=2, ensure_ascii=False)
    return ""
