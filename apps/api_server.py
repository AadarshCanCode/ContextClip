"""
apps/api_server.py - local-only API for the Electron desktop shell.

The Python agent remains the source of truth. This module exposes a small
HTTP/WebSocket bridge so Electron can render real captured state without
reimplementing clipboard, graph, privacy, Exa, or OpenRouter logic.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from apps.agent import ContextClipAgent, DATA_DIR
from cloud.clipboard_analyzer import analyze_event_context
from core.action_router import BubbleActionDefinition, get_bubble_actions
from core.actions import BackendActionBroker, BackendActionError, BackendActionResult
from core.contracts import ContextBlock, Event, EventType
from core.privacy import safe_preview


DEFAULT_APPS = [
    {"family": "outlook", "name": "Outlook", "kind": "communication"},
    {"family": "teams", "name": "Teams", "kind": "communication"},
    {"family": "word", "name": "Word", "kind": "document"},
    {"family": "powerpoint", "name": "PowerPoint", "kind": "presentation"},
    {"family": "excel", "name": "Excel", "kind": "spreadsheet"},
    {"family": "browser_chrome", "name": "Browser", "kind": "browser"},
    {"family": "browser_edge", "name": "Browser", "kind": "browser"},
    {"family": "vs_code", "name": "VS Code", "kind": "code"},
    {"family": "terminal", "name": "Terminal", "kind": "terminal"},
]


class RunActionRequest(BaseModel):
    action_id: str
    args: dict[str, Any] = Field(default_factory=dict)


class EventBroadcaster:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._latest: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        with self._lock:
            self._clients.add(queue)
            latest = list(self._latest[-10:])
        for item in latest:
            await queue.put(item)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.discard(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._latest.append(payload)
            self._latest = self._latest[-40:]
            clients = list(self._clients)

        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for queue in clients:
            loop.call_soon_threadsafe(self._put_latest, queue, payload)

    @staticmethod
    def _put_latest(queue: asyncio.Queue[dict[str, Any]], payload: dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(payload)


class ContextClipApiRuntime:
    def __init__(self, agent: ContextClipAgent, start_agent: bool = True) -> None:
        self.agent = agent
        self.broker = BackendActionBroker(agent)
        self.start_agent = start_agent
        self.broadcaster = EventBroadcaster()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.broadcaster.attach_loop(asyncio.get_running_loop())
        if self.start_agent:
            self.agent.start_background()
        self._started = True

    def stop(self) -> None:
        if self.start_agent:
            self.agent.stop()
        self._started = False

    def handle_event(self, event: Event) -> None:
        payload = _event_payload(event)
        if event.type == EventType.PASTE:
            self.broadcaster.publish({
                "type": "paste",
                "event": payload,
                "bubble": {"visible": False, "reason": "paste"},
            })
            return

        self.broadcaster.publish({
            "type": "copy",
            "event": payload,
            "bubble": _bubble_payload(event, phase="captured"),
        })
        threading.Thread(target=self._analyze_and_publish, args=(event,), daemon=True).start()

    def handle_context_block(self, block: ContextBlock) -> None:
        self.broadcaster.publish({"type": "context_block", "block": block.to_dict()})

    def run_action(self, request: RunActionRequest) -> BackendActionResult:
        try:
            result = self.broker.execute(request.action_id, **request.args)
        except BackendActionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        self.broadcaster.publish({"type": "action_result", "result": result.to_dict()})
        return result

    def _analyze_and_publish(self, event: Event) -> None:
        try:
            screenshot_path = self.agent.get_screenshot_path(event.screenshot_id) if event.screenshot_id else None
            context = analyze_event_context(event, screenshot_path=screenshot_path)
            actions = [_action_payload(action) for action in get_bubble_actions(context)[:3]]
            self.broadcaster.publish({
                "type": "copy_analysis",
                "event": _event_payload(event),
                "context": context.to_dict(),
                "actions": actions,
                "bubble": _bubble_payload(event, phase="ready", context=context.to_dict(), actions=actions),
            })
        except Exception as exc:
            self.broadcaster.publish({
                "type": "copy_analysis",
                "event": _event_payload(event),
                "context": None,
                "actions": [],
                "error": str(exc),
                "bubble": _bubble_payload(event, phase="error"),
            })


def create_app(
    *,
    agent: Optional[ContextClipAgent] = None,
    data_dir: Path = DATA_DIR,
    start_agent: bool = True,
) -> FastAPI:
    runtime_agent = agent or ContextClipAgent(data_dir=data_dir)
    runtime = ContextClipApiRuntime(runtime_agent, start_agent=start_agent)
    runtime_agent._on_event = runtime.handle_event
    runtime_agent._on_block = runtime.handle_context_block

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(title="ContextClip Desktop API", version="0.1.0", lifespan=lifespan)
    app.state.runtime = runtime

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "file://"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "contextclip",
            "agent_running": runtime.agent._running,
            "data_dir": str(data_dir.resolve()),
        }

    @app.get("/events/recent")
    def recent_events(limit: int = 30) -> dict[str, Any]:
        bounded = max(1, min(int(limit or 30), 100))
        events = runtime.agent.get_recent_events(bounded)
        return {"events": [_event_payload(event) for event in events]}

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        return runtime.agent.get_stats()

    @app.get("/apps")
    def apps() -> dict[str, Any]:
        usage = {row.get("family"): row for row in runtime.agent.get_app_families()}
        cards = []
        seen = set()
        for item in DEFAULT_APPS:
            family = item["family"]
            row = usage.get(family, {})
            seen.add(family)
            cards.append({
                **item,
                "connected": True,
                "event_count": int(row.get("event_count") or 0),
                "copies": int(row.get("copies") or 0),
                "pastes": int(row.get("pastes") or 0),
            })
        for family, row in usage.items():
            if family in seen:
                continue
            cards.append({
                "family": family or "unknown",
                "name": _pretty_family(family or "unknown"),
                "kind": "observed",
                "connected": True,
                "event_count": int(row.get("event_count") or 0),
                "copies": int(row.get("copies") or 0),
                "pastes": int(row.get("pastes") or 0),
            })
        return {"apps": cards}

    @app.get("/actions")
    def actions() -> dict[str, Any]:
        return {"actions": [action.to_dict() for action in runtime.broker.discover()]}

    @app.post("/actions/run")
    def run_action(request: RunActionRequest) -> dict[str, Any]:
        return runtime.run_action(request).to_dict()

    @app.get("/settings/status")
    def settings_status() -> dict[str, Any]:
        from cloud.google_calendar import google_calendar_status

        return {
            "openrouter": {
                "configured": bool(os.environ.get("OPENROUTER_API_KEY")),
                "model": os.environ.get("OPENROUTER_MODEL", ""),
                "analyzer_model": os.environ.get("OPENROUTER_ANALYZER_MODEL", ""),
                "action_model": os.environ.get("OPENROUTER_ACTION_MODEL", ""),
            },
            "exa": {
                "configured": bool(os.environ.get("EXA_API_KEY")),
                "search_type": os.environ.get("EXA_SEARCH_TYPE", "auto"),
                "num_results": int(os.environ.get("EXA_NUM_RESULTS", "10") or 10),
            },
            "calendar": google_calendar_status(),
            "capture": {
                "data_dir": str(data_dir.resolve()),
                "copy_settle_ms": int(os.environ.get("CONTEXTCLIP_COPY_SETTLE_MS", "120") or 120),
                "clipboard_poll_ms": int(os.environ.get("CONTEXTCLIP_POLL_CLIPBOARD_MS", "250") or 250),
                "screenshot_mode": os.environ.get("CONTEXTCLIP_SCREENSHOT_MODE", "active_window"),
                "bubble_auto_hide_ms": int(os.environ.get("CONTEXTCLIP_BUBBLE_AUTO_HIDE_MS", "12000") or 12000),
            },
        }

    @app.websocket("/events")
    async def events_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = await runtime.broadcaster.subscribe()
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            runtime.broadcaster.unsubscribe(queue)

    return app


def run_api_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def _event_payload(event: Event) -> dict[str, Any]:
    data = event.to_dict()
    data["anchor"] = _event_anchor(event)
    data["display"] = {
        "title": _event_title(event),
        "source": _source_label(event),
        "preview": safe_preview(event.clipboard.preview_text, 140),
        "time": event.time_label,
    }
    data["clipboard"].pop("raw_text", None)
    return data


def _bubble_payload(
    event: Event,
    *,
    phase: str,
    context: Optional[dict[str, Any]] = None,
    actions: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    return {
        "visible": event.type == EventType.COPY,
        "phase": phase,
        "anchor": _event_anchor(event),
        "title": "Copy captured" if phase == "captured" else (context or {}).get("intent", "Context ready"),
        "subtitle": safe_preview((context or {}).get("summary") or event.clipboard.preview_text, 140),
        "source": _source_label(event),
        "content_type": event.content_type,
        "event_id": event.id,
        "actions": actions or [],
    }


def _event_anchor(event: Event) -> Optional[dict[str, int]]:
    context = event.plugin_context or {}
    capture = context.get("capture") if isinstance(context, dict) else None
    position = None
    if isinstance(capture, dict):
        position = capture.get("anchor_position") or capture.get("cursor_position")
    if not isinstance(position, dict):
        return None
    try:
        return {"x": int(position["x"]), "y": int(position["y"])}
    except (KeyError, TypeError, ValueError):
        return None


def _action_payload(action: BubbleActionDefinition) -> dict[str, str]:
    return {
        "action_id": action.action_id,
        "label": action.label,
        "backend_action_id": action.backend_action_id,
        "description": action.description,
    }


def _event_title(event: Event) -> str:
    source = _source_label(event)
    verb = "copied" if event.type == EventType.COPY else "pasted"
    return f"{source} {verb}"


def _source_label(event: Event) -> str:
    app = event.source_app
    family_labels = {
        "browser_chrome": "Google Chrome",
        "browser_edge": "Microsoft Edge",
        "browser_firefox": "Firefox",
        "browser_brave": "Brave",
        "browser_opera": "Opera",
        "browser_opera_gx": "Opera GX",
        "browser_vivaldi": "Vivaldi",
        "browser_arc": "Arc",
        "browser_zen": "Zen Browser",
        "browser_chromium": "Chromium",
        "vs_code": "VS Code",
        "notepad_plus": "Notepad++",
    }
    family = (app.app_family or "").lower()
    if family and family != "unknown":
        return family_labels.get(family, _pretty_family(family))

    process = (app.process_name or "").strip()
    if process:
        process_name = re.split(r"[\\/]", process)[-1]
        process_name = re.sub(r"\.exe$", "", process_name, flags=re.IGNORECASE)
        if process_name:
            return _pretty_family(process_name.replace("-", "_"))

    title = (app.window_title or "").strip()
    if title:
        return title.split(" - ")[-1].strip() or title
    return "Desktop"


def _pretty_family(value: str) -> str:
    return (value or "Unknown").replace("_", " ").title()
