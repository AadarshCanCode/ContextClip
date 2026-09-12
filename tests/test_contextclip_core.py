from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CONTEXTCLIP_DISABLE_DOTENV", "1")

from core.actions import BackendActionBroker
from core.action_router import get_bubble_action_ids
from core.config import load_env_file
from core.context_engine import analyze_clipboard_locally
from core.contracts import (
    AppRef,
    ClipboardPayload,
    Event,
    EventType,
    PasteMode,
    PayloadType,
    PrivacyClass,
)
from core.graph import ReferenceGraph
from core.memory import ContextWindowManager
from cloud.exa_search import ExaReferenceSearch, ExaSearchError
from storage.database import close_connection, initialize
from storage.repositories import ContextBlockRepository, EventRepository, GraphEdgeRepository


def _payload(text: str) -> ClipboardPayload:
    return ClipboardPayload(
        payload_hash=ClipboardPayload.compute_hash(text),
        payload_type=PayloadType.TEXT,
        preview_text=text[:240],
        raw_text=text,
        byte_size=len(text.encode("utf-8")),
    )


def _app(family: str) -> AppRef:
    return AppRef(
        process_name=f"{family}.exe",
        app_family=family,
        window_title=f"{family} window",
    )


def _event(
    event_id: str,
    seq: int,
    event_type: EventType,
    family: str,
    text: str,
    workflow_id: str = "w_test",
) -> Event:
    app = _app(family)
    return Event(
        id=event_id,
        seq=seq,
        type=event_type,
        timestamp_utc=f"2026-09-12T10:0{seq}:00+00:00",
        source_app=app,
        destination_app=app if event_type == EventType.PASTE else None,
        clipboard=_payload(text),
        screenshot_id=None,
        privacy_class=PrivacyClass.PUBLIC,
        confidence=1.0,
        workflow_id=workflow_id,
        paste_mode=PasteMode.INFERRED if event_type == EventType.PASTE else None,
        content_type="text",
    )


class FakeExaClient:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {
            "results": [
                {
                    "title": "Docker connection refused troubleshooting",
                    "url": "https://example.com/docker-connection-refused",
                    "highlights": ["Check that the API container is listening on the target port."],
                    "publishedDate": "2026-01-01",
                    "score": 0.91,
                }
            ],
            "costDollars": {"total": 0.001},
        }


class FakeActionAgent:
    def get_stats(self):
        return {"events_total": 0, "copies": 0, "pastes": 0, "latest_seq": 0}

    def get_app_families(self):
        return []

    def dump_llm_context(self):
        return {"toon": "window[0]", "events": [], "stats": self.get_stats(), "context_blocks": []}

    def export_active_context_markdown(self, n=7):
        return "## ContextClip Active Context"

    def copy_active_context_markdown(self, n=7):
        return self.export_active_context_markdown(n)

    def get_all_edges(self):
        return []

    def summarize_graph(self):
        return "No graph edges yet."

    def search_clipboard_references(self, **kwargs):
        raise ExaSearchError("Set EXA_API_KEY before searching clipboard references.")

    def record_current_clipboard_copy(self):
        return None

    def record_current_clipboard_paste(self):
        return None


class ContextClipCoreTests(unittest.TestCase):
    def _repos(self, root: Path):
        db_path = root / "contextclip.db"
        initialize(db_path)
        return (
            EventRepository(db_path),
            GraphEdgeRepository(db_path),
            ContextBlockRepository(db_path),
        )

    def test_paste_source_lookup_happens_before_edge_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                events, edges, _blocks = self._repos(Path(tmp))
                graph = ReferenceGraph(events, edges)

                copy = _event("evt_copy", 1, EventType.COPY, "vs_code", "ERR_CONNECTION_REFUSED 10.0.0.42:8080")
                events.insert(copy)
                graph.record_copy(copy)

                paste = _event("evt_paste", 2, EventType.PASTE, "browser_edge", copy.clipboard.raw_text)
                source_id = graph.find_source_for_paste(paste)
                self.assertEqual(source_id, copy.id)
                self.assertEqual(edges.get_all(), [])

                paste.parent_event_id = source_id
                events.insert(paste)
                graph.record_paste(paste, source_id)

                stored_edges = edges.get_all()
                self.assertEqual(len(stored_edges), 1)
                self.assertEqual(stored_edges[0].from_event_id, copy.id)
                self.assertEqual(stored_edges[0].to_event_id, paste.id)
                self.assertEqual(stored_edges[0].relation.value, "pasted_into")
            finally:
                close_connection()

    def test_exa_reference_search_uses_highlights_for_clipboard_text(self):
        client = FakeExaClient()
        service = ExaReferenceSearch(client=client)

        result = service.search_text(
            "ERR_CONNECTION_REFUSED 10.0.0.42:8080",
            search_type="auto",
            num_results=5,
            include_domains=["docs.docker.com"],
            max_age_hours=24,
        )

        self.assertEqual(result.source, "exa")
        self.assertEqual(result.search_type, "auto")
        self.assertEqual(result.results[0].title, "Docker connection refused troubleshooting")
        query, kwargs = client.calls[0]
        self.assertIn("ERR_CONNECTION_REFUSED", query)
        self.assertEqual(kwargs["type"], "auto")
        self.assertEqual(kwargs["num_results"], 5)
        self.assertEqual(kwargs["include_domains"], ["docs.docker.com"])
        self.assertEqual(kwargs["contents"], {"highlights": True, "max_age_hours": 24})

    def test_exa_reference_search_blocks_restricted_clipboard_content(self):
        client = FakeExaClient()
        service = ExaReferenceSearch(client=client)

        with self.assertRaises(ExaSearchError):
            service.search_text("OPENROUTER_API_KEY=sk-or-v1-secret123")

        self.assertEqual(client.calls, [])

    def test_seven_event_window_creates_heuristic_block_without_openrouter_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                events, _edges, blocks = self._repos(Path(tmp))
                manager = ContextWindowManager(events, blocks)

                created = None
                with patch.dict(os.environ, {"CONTEXTCLIP_DISABLE_DOTENV": "1"}, clear=True):
                    for idx in range(1, 8):
                        event_type = EventType.COPY if idx % 2 else EventType.PASTE
                        event = _event(
                            f"evt_{idx}",
                            idx,
                            event_type,
                            "vs_code" if idx in (1, 6, 7) else "browser_edge",
                            f"clipboard payload {idx}",
                        )
                        events.insert(event)
                        created = manager.push(event)

                self.assertIsNotNone(created)
                self.assertEqual(created.event_start, 1)
                self.assertEqual(created.event_end, 7)
                self.assertEqual(len(created.event_ids), 7)
                self.assertIn("window[7]", created.toon_payload)
                self.assertIn("ContextClip", created.markdown_payload)
                self.assertEqual(blocks.get_latest(1)[0].model_info["method"], "heuristic")
            finally:
                close_connection()

    def test_env_loader_does_not_override_existing_shell_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "OPENROUTER_MODEL=file-model\nEXA_NUM_RESULTS=4\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENROUTER_MODEL": "shell-model"}, clear=True):
                loaded = load_env_file(env_path)

                self.assertEqual(loaded["OPENROUTER_MODEL"], "file-model")
                self.assertEqual(os.environ["OPENROUTER_MODEL"], "shell-model")
                self.assertEqual(os.environ["EXA_NUM_RESULTS"], "4")

    def test_backend_action_broker_lists_and_executes_real_actions(self):
        broker = BackendActionBroker(FakeActionAgent())
        action_ids = {action.id for action in broker.discover()}

        self.assertIn("storage.stats", action_ids)
        self.assertIn("references.search_clipboard", action_ids)
        self.assertIn("ai.explain_clipboard", action_ids)

        stats = broker.execute("storage.stats")
        self.assertTrue(stats.success)
        self.assertEqual(stats.data["stats"]["events_total"], 0)

        search = broker.execute("references.search_clipboard")
        self.assertFalse(search.success)
        self.assertIn("EXA_API_KEY", search.message)

    def test_bubble_router_maps_local_context_to_concrete_actions(self):
        error_context = analyze_clipboard_locally("ECONNREFUSED 127.0.0.1:5432")
        url_context = analyze_clipboard_locally("https://docs.exa.ai/reference/search-api-guide-for-coding-agents")

        self.assertEqual(error_context.content_type, "error")
        self.assertEqual(get_bubble_action_ids(error_context), ["help_fix", "explain", "search_references"])
        self.assertEqual(url_context.content_type, "url")
        self.assertEqual(get_bubble_action_ids(url_context), ["open", "summarize", "search_references"])


if __name__ == "__main__":
    unittest.main()
