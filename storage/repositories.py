"""
storage/repositories.py — Repository layer over SQLite.

Each repository is a thin, dependency-inverted adapter.
Core code calls repository interfaces; this file is the only
place that knows about SQLite.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage.database import get_connection
from core.contracts import (
    AppRef, ClipboardPayload, ContentType, ContextBlock, EdgeRelation,
    Event, EventType, GraphEdge, PasteMode, PayloadType, PrivacyClass,
    ScreenshotRef,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


# ---------------------------------------------------------------------------
# Event Repository
# ---------------------------------------------------------------------------

class EventRepository:
    def __init__(self, db_path: Path) -> None:
        self._db = db_path

    def _conn(self):
        return get_connection(self._db)

    def next_seq(self) -> int:
        row = self._conn().execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
        return (row[0] or 0) + 1

    def insert(self, event: Event) -> None:
        conn = self._conn()
        conn.execute(
            """
            INSERT OR IGNORE INTO events(
                id, seq, workflow_id, type, timestamp_utc,
                source_app_json, dest_app_json,
                payload_hash, payload_type, preview_text, raw_text, byte_size,
                screenshot_id, plugin_context_json, entities_json,
                parent_event_id, paste_mode, content_type,
                privacy_class, confidence
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.id,
                event.seq,
                event.workflow_id,
                event.type.value,
                event.timestamp_utc,
                json.dumps(event.source_app.to_dict()),
                json.dumps(event.destination_app.to_dict()) if event.destination_app else None,
                event.clipboard.payload_hash,
                event.clipboard.payload_type.value,
                event.clipboard.preview_text,
                event.clipboard.raw_text,
                event.clipboard.byte_size,
                event.screenshot_id,
                json.dumps(event.plugin_context) if event.plugin_context else None,
                json.dumps(event.entities),
                event.parent_event_id,
                event.paste_mode.value if event.paste_mode else None,
                event.content_type,
                event.privacy_class.value,
                event.confidence,
            ),
        )
        conn.commit()

    def get_by_id(self, event_id: str) -> Optional[Event]:
        row = self._conn().execute(
            "SELECT * FROM events WHERE id=?", (event_id,)
        ).fetchone()
        return self._row_to_event(row) if row else None

    def get_recent(self, limit: int = 50) -> List[Event]:
        rows = self._conn().execute(
            "SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_event(r) for r in reversed(rows)]

    def get_last_n(self, n: int = 7) -> List[Event]:
        rows = self._conn().execute(
            "SELECT * FROM events ORDER BY seq DESC LIMIT ?", (n,)
        ).fetchall()
        return list(reversed([self._row_to_event(r) for r in rows]))

    def find_recent_copy_by_hash(self, payload_hash: str) -> Optional[Event]:
        row = self._conn().execute(
            """
            SELECT * FROM events
            WHERE type='copy' AND payload_hash=?
            ORDER BY seq DESC
            LIMIT 1
            """,
            (payload_hash,),
        ).fetchone()
        return self._row_to_event(row) if row else None

    def get_by_workflow(self, workflow_id: str) -> List[Event]:
        rows = self._conn().execute(
            "SELECT * FROM events WHERE workflow_id=? ORDER BY seq", (workflow_id,)
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        conn = self._conn()
        today = datetime.now(timezone.utc).date().isoformat()
        copies_today = conn.execute(
            "SELECT COUNT(*) FROM events WHERE type='copy' AND timestamp_utc >= ?",
            (today,),
        ).fetchone()[0]
        pastes_today = conn.execute(
            "SELECT COUNT(*) FROM events WHERE type='paste' AND timestamp_utc >= ?",
            (today,),
        ).fetchone()[0]
        total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        unique_apps = conn.execute(
            "SELECT COUNT(DISTINCT json_extract(source_app_json,'$.app_family')) FROM events"
        ).fetchone()[0]
        return {
            "copies_today": copies_today,
            "pastes_today": pastes_today,
            "total_events": total_events,
            "unique_apps": unique_apps,
        }

    def search_fts(self, query: str, limit: int = 20) -> List[Event]:
        rows = self._conn().execute(
            "SELECT e.* FROM events e JOIN events_fts f ON e.id=f.id WHERE events_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_app_families(self) -> List[Dict[str, Any]]:
        rows = self._conn().execute(
            """
            SELECT json_extract(source_app_json,'$.app_family') AS family,
                   COUNT(*) AS event_count,
                   SUM(CASE WHEN type='copy' THEN 1 ELSE 0 END) AS copies,
                   SUM(CASE WHEN type='paste' THEN 1 ELSE 0 END) AS pastes
            FROM events
            GROUP BY family
            ORDER BY event_count DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def _row_to_event(self, row) -> Event:
        src = AppRef.from_dict(json.loads(row["source_app_json"]))
        dst_raw = row["dest_app_json"]
        dst = AppRef.from_dict(json.loads(dst_raw)) if dst_raw else None
        ctx_raw = row["plugin_context_json"]
        clipboard = ClipboardPayload(
            payload_hash=row["payload_hash"],
            payload_type=PayloadType(row["payload_type"]),
            preview_text=row["preview_text"],
            raw_text=row["raw_text"],
            byte_size=row["byte_size"],
        )
        return Event(
            id=row["id"],
            seq=row["seq"],
            type=EventType(row["type"]),
            timestamp_utc=row["timestamp_utc"],
            source_app=src,
            clipboard=clipboard,
            screenshot_id=row["screenshot_id"],
            privacy_class=PrivacyClass(row["privacy_class"]),
            confidence=row["confidence"],
            destination_app=dst,
            plugin_context=json.loads(ctx_raw) if ctx_raw else None,
            entities=json.loads(row["entities_json"]),
            workflow_id=row["workflow_id"],
            parent_event_id=row["parent_event_id"],
            paste_mode=PasteMode(row["paste_mode"]) if row["paste_mode"] else None,
            content_type=row["content_type"],
        )


# ---------------------------------------------------------------------------
# Screenshot Repository
# ---------------------------------------------------------------------------

class ScreenshotRepository:
    def __init__(self, db_path: Path) -> None:
        self._db = db_path

    def _conn(self):
        return get_connection(self._db)

    def insert(self, ref: ScreenshotRef) -> ScreenshotRef:
        conn = self._conn()
        conn.execute(
            """
            INSERT OR IGNORE INTO screenshots(id, sha256, local_path, width, height, created_at, retention_class)
            VALUES (?,?,?,?,?,?,?)
            """,
            (ref.id, ref.sha256, ref.local_path, ref.width, ref.height, ref.created_at, ref.retention_class),
        )
        conn.commit()
        return self.get_by_id(ref.id) or self.get_by_hash(ref.sha256) or ref

    def get_by_id(self, screenshot_id: str) -> Optional[ScreenshotRef]:
        row = self._conn().execute(
            "SELECT * FROM screenshots WHERE id=?", (screenshot_id,)
        ).fetchone()
        if not row:
            return None
        return ScreenshotRef(
            id=row["id"],
            sha256=row["sha256"],
            local_path=row["local_path"],
            width=row["width"],
            height=row["height"],
            created_at=row["created_at"],
            retention_class=row["retention_class"],
        )

    def get_by_hash(self, sha256: str) -> Optional[ScreenshotRef]:
        row = self._conn().execute(
            "SELECT * FROM screenshots WHERE sha256=?", (sha256,)
        ).fetchone()
        if not row:
            return None
        return ScreenshotRef(
            id=row["id"], sha256=row["sha256"], local_path=row["local_path"],
            width=row["width"], height=row["height"], created_at=row["created_at"],
            retention_class=row["retention_class"],
        )


# ---------------------------------------------------------------------------
# Graph Edge Repository
# ---------------------------------------------------------------------------

class GraphEdgeRepository:
    def __init__(self, db_path: Path) -> None:
        self._db = db_path

    def _conn(self):
        return get_connection(self._db)

    def insert(self, edge: GraphEdge) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO graph_edges(id,from_event_id,to_event_id,relation,score,source) VALUES(?,?,?,?,?,?)",
            (edge.id, edge.from_event_id, edge.to_event_id, edge.relation.value, edge.score, edge.source),
        )
        conn.commit()

    def get_neighbors(self, event_id: str, depth: int = 1) -> List[GraphEdge]:
        rows = self._conn().execute(
            "SELECT * FROM graph_edges WHERE from_event_id=? OR to_event_id=?",
            (event_id, event_id),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def get_all(self) -> List[GraphEdge]:
        rows = self._conn().execute("SELECT * FROM graph_edges ORDER BY rowid").fetchall()
        return [self._row_to_edge(r) for r in rows]

    def _row_to_edge(self, row) -> GraphEdge:
        return GraphEdge(
            id=row["id"],
            from_event_id=row["from_event_id"],
            to_event_id=row["to_event_id"],
            relation=EdgeRelation(row["relation"]),
            score=row["score"],
            source=row["source"],
        )


# ---------------------------------------------------------------------------
# Context Block Repository
# ---------------------------------------------------------------------------

class ContextBlockRepository:
    def __init__(self, db_path: Path) -> None:
        self._db = db_path

    def _conn(self):
        return get_connection(self._db)

    def insert(self, block: ContextBlock) -> None:
        conn = self._conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO context_blocks(
                id, workflow_id, event_start, event_end, event_ids_json,
                title, one_line_goal, narrative, entities_json, decisions_json,
                questions_json, transitions_json, hashes_json,
                toon_payload, markdown_payload, model_info_json, safety_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                block.id, block.workflow_id, block.event_start, block.event_end,
                json.dumps(block.event_ids), block.title, block.one_line_goal,
                block.narrative, json.dumps(block.important_entities),
                json.dumps(block.decisions), json.dumps(block.open_questions),
                json.dumps(block.app_transitions), json.dumps(block.source_hashes),
                block.toon_payload, block.markdown_payload,
                json.dumps(block.model_info), json.dumps(block.safety_redactions),
                block.created_at,
            ),
        )
        conn.commit()

    def get_all(self) -> List[ContextBlock]:
        rows = self._conn().execute(
            "SELECT * FROM context_blocks ORDER BY event_start"
        ).fetchall()
        return [self._row_to_block(r) for r in rows]

    def get_latest(self, n: int = 5) -> List[ContextBlock]:
        rows = self._conn().execute(
            "SELECT * FROM context_blocks ORDER BY event_start DESC LIMIT ?", (n,)
        ).fetchall()
        return list(reversed([self._row_to_block(r) for r in rows]))

    def _row_to_block(self, row) -> ContextBlock:
        return ContextBlock(
            id=row["id"],
            workflow_id=row["workflow_id"],
            event_start=row["event_start"],
            event_end=row["event_end"],
            event_ids=json.loads(row["event_ids_json"]),
            title=row["title"],
            one_line_goal=row["one_line_goal"],
            narrative=row["narrative"],
            important_entities=json.loads(row["entities_json"]),
            decisions=json.loads(row["decisions_json"]),
            open_questions=json.loads(row["questions_json"]),
            app_transitions=json.loads(row["transitions_json"]),
            source_hashes=json.loads(row["hashes_json"]),
            toon_payload=row["toon_payload"],
            markdown_payload=row["markdown_payload"],
            model_info=json.loads(row["model_info_json"]),
            safety_redactions=json.loads(row["safety_json"]),
            created_at=row["created_at"],
        )
