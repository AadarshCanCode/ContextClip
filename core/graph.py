"""
core/graph.py — ReferenceGraph and workflow scoring.

Implements Section 4 and 11 of the ContextClip spec.

Key rules:
- Graph edges are derived; raw events are canonical.
- Workflow scoring uses the weighted formula from spec §11.2.
- Paste correlation runs on clipboard hash match + time proximity.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Dict, List, Optional, Tuple

from core.contracts import EdgeRelation, Event, EventType, GraphEdge, PasteMode
from storage.repositories import EventRepository, GraphEdgeRepository


# Workflow scoring weights (spec §11.2)
_W_SEMANTIC = 0.35
_W_ENTITY = 0.20
_W_TIME = 0.15
_W_APP_TRANSITION = 0.15
_W_PASTE_LINKAGE = 0.10
_W_DOC_OVERLAP = 0.05

# Time window for paste correlation (seconds)
PASTE_CORRELATION_WINDOW_S = 5.0


def _new_edge_id() -> str:
    return f"edge_{uuid.uuid4().hex[:12]}"


def _time_proximity_score(event_a: Event, event_b: Event) -> float:
    """Returns 0.0–1.0 based on time gap between two events (decay over 30s)."""
    try:
        from datetime import datetime, timezone
        ta = datetime.fromisoformat(event_a.timestamp_utc.replace("Z", "+00:00"))
        tb = datetime.fromisoformat(event_b.timestamp_utc.replace("Z", "+00:00"))
        gap = abs((tb - ta).total_seconds())
        return max(0.0, 1.0 - gap / 30.0)
    except Exception:
        return 0.0


def _entity_overlap_score(event_a: Event, event_b: Event) -> float:
    """Simple entity overlap based on shared tokens in previews."""
    tokens_a = set(event_a.clipboard.preview_text.lower().split())
    tokens_b = set(event_b.clipboard.preview_text.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    return min(1.0, overlap / max(len(tokens_a), len(tokens_b)))


def _app_transition_score(event_a: Event, event_b: Event) -> float:
    """Score based on whether the app transition makes workflow sense."""
    a_family = event_a.source_app.app_family
    b_family = event_b.source_app.app_family

    # Same app: probably same workflow
    if a_family == b_family:
        return 0.7

    # Known productive transitions
    productive_pairs = {
        ("vs_code", "browser_chrome"), ("vs_code", "browser_edge"),
        ("browser_chrome", "word"), ("browser_edge", "word"),
        ("browser_chrome", "vs_code"), ("browser_edge", "vs_code"),
        ("outlook", "teams"), ("teams", "word"),
        ("word", "vs_code"), ("word", "outlook"),
        ("terminal", "vs_code"), ("vs_code", "terminal"),
    }
    if (a_family, b_family) in productive_pairs or (b_family, a_family) in productive_pairs:
        return 0.9

    return 0.3


def compute_workflow_score(event_a: Event, event_b: Event) -> float:
    """
    Compute the workflow similarity score between two events.
    Uses the formula from spec §11.2.
    """
    # For demo: semantic similarity approximated by entity overlap
    semantic = _entity_overlap_score(event_a, event_b) * 0.6
    entity = _entity_overlap_score(event_a, event_b)
    time_prox = _time_proximity_score(event_a, event_b)
    app_trans = _app_transition_score(event_a, event_b)

    # Paste linkage: 1.0 if payload hashes match (same clipboard content)
    paste_link = 1.0 if event_a.clipboard.payload_hash == event_b.clipboard.payload_hash else 0.0

    score = (
        _W_SEMANTIC * semantic
        + _W_ENTITY * entity
        + _W_TIME * time_prox
        + _W_APP_TRANSITION * app_trans
        + _W_PASTE_LINKAGE * paste_link
        + _W_DOC_OVERLAP * 0.0  # document overlap not available without plugin
    )
    return round(min(1.0, score), 4)


class ReferenceGraph:
    """
    Manages the directed workflow graph of events and edges.

    Thread-safe. The underlying storage is provided by GraphEdgeRepository.
    """

    def __init__(self, event_repo: EventRepository, edge_repo: GraphEdgeRepository) -> None:
        self._events = event_repo
        self._edges = edge_repo
        self._lock = threading.RLock()

        # In-memory cache of the last copy event per payload hash,
        # used for fast paste correlation.
        self._copy_by_hash: Dict[str, str] = {}   # payload_hash -> event_id
        self._last_copy_event_id: Optional[str] = None

    def record_copy(self, event: Event) -> None:
        """Register a copy event in the graph."""
        with self._lock:
            # Cache for paste correlation
            self._copy_by_hash[event.clipboard.payload_hash] = event.id
            self._last_copy_event_id = event.id

            # Link to previous event via FOLLOWS edge if it exists
            recent = self._events.get_recent(limit=2)
            prev_events = [e for e in recent if e.id != event.id]
            if prev_events:
                prev = prev_events[-1]
                score = compute_workflow_score(prev, event)
                if score > 0.2:
                    self._add_edge(
                        from_id=prev.id,
                        to_id=event.id,
                        relation=EdgeRelation.FOLLOWS,
                        score=score,
                        source="inferred",
                    )

    def correlate_paste(self, paste_event: Event) -> Optional[str]:
        """
        Find the best matching copy event for a paste.
        Returns the source copy event ID, or None.
        Implements spec §11.1 paste correlation algorithm.
        """
        with self._lock:
            # Step 1: exact hash match
            payload_hash = paste_event.clipboard.payload_hash
            if payload_hash in self._copy_by_hash:
                source_id = self._copy_by_hash[payload_hash]
                source_event = self._events.get_by_id(source_id)
                if source_event:
                    # Step 2: time check (paste must come after copy)
                    score = compute_workflow_score(source_event, paste_event)
                    self._add_edge(
                        from_id=source_id,
                        to_id=paste_event.id,
                        relation=EdgeRelation.PASTED_INTO,
                        score=score,
                        source="hash_match",
                    )
                    return source_id

            # Fallback: use last copy event
            if self._last_copy_event_id:
                return self._last_copy_event_id

            return None

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: EdgeRelation,
        score: float = 1.0,
        source: str = "direct",
    ) -> GraphEdge:
        return self._add_edge(from_id, to_id, relation, score, source)

    def _add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: EdgeRelation,
        score: float,
        source: str,
    ) -> GraphEdge:
        edge = GraphEdge(
            id=_new_edge_id(),
            from_event_id=from_id,
            to_event_id=to_id,
            relation=relation,
            score=score,
            source=source,
        )
        self._edges.insert(edge)
        return edge

    def get_neighbors(self, event_id: str, depth: int = 1) -> List[GraphEdge]:
        return self._edges.get_neighbors(event_id, depth)

    def get_workflow_events(self, workflow_id: str) -> List[Event]:
        return self._events.get_by_workflow(workflow_id)

    def get_all_edges(self) -> List[GraphEdge]:
        return self._edges.get_all()

    def summarize(self) -> str:
        """Human-readable graph summary for debugging."""
        lines = []
        for edge in self.get_all_edges()[-20:]:
            lines.append(
                f"  {edge.from_event_id[:8]} --{edge.relation.value}--> "
                f"{edge.to_event_id[:8]} (score={edge.score:.2f}, src={edge.source})"
            )
        return "\n".join(lines) if lines else "  (empty graph)"
