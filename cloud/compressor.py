"""
cloud/compressor.py — Cloud context compression service adapter.

Implements spec §12. Uses OpenAI (or compatible) to compress a 7-event
window into a structured ContextBlock. Falls back to heuristic compression
when OPENAI_API_KEY is not set or the request fails.

Pipeline (spec §12.1):
  local event window
    -> policy filter
    -> compact domain JSON
    -> TOON encoder
    -> model prompt
    -> structured model output
    -> schema validator
    -> safety/redaction pass
    -> ContextBlock
    -> local persistence
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from core.contracts import ContextBlock, Event
from cloud.toon import encode_events_toon
from cloud.markdown_export import export_events_markdown


SYSTEM_PROMPT = """You are ContextClip, a workflow memory agent.
You receive a TOON-encoded window of 7 clipboard/paste events.
Your job is to produce a structured JSON context block.

Rules:
- Summarize the user workflow, not individual screenshots.
- Preserve exact technical identifiers, commands, URLs and error strings.
- Distinguish observed facts from inferred intent.
- Do not invent app transitions not present in the events.
- Return event IDs for every claim from a specific event.
- Return a compact narrative optimized for later retrieval.

Return valid JSON matching this schema exactly:
{
  "one_line_goal": "string (≤80 chars)",
  "narrative": "string (2-4 sentences)",
  "important_entities": ["string"],
  "decisions": ["string"],
  "open_questions": ["string"],
  "app_transitions": ["app1 -> app2"]
}"""


def compress_with_llm(events: List[Event], block_num: int) -> ContextBlock:
    """
    Compress events into a ContextBlock using an LLM.
    Falls back to heuristic compression if LLM is unavailable.
    """
    api_key = os.environ.get("OPENAI_API_KEY")

    if api_key:
        try:
            return _llm_compress(events, block_num, api_key)
        except Exception as exc:
            print(f"[Compressor] LLM compression failed ({exc}), using heuristics.")

    # Heuristic fallback (always available offline)
    return _heuristic_compress(events, block_num)


def _llm_compress(events: List[Event], block_num: int, api_key: str) -> ContextBlock:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    toon = encode_events_toon(events)
    user_msg = f"TOON payload:\n{toon}\n\nProduce the structured JSON context block."

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=600,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    return _build_block(
        events=events,
        block_num=block_num,
        one_line_goal=data.get("one_line_goal", ""),
        narrative=data.get("narrative", ""),
        entities=data.get("important_entities", []),
        decisions=data.get("decisions", []),
        questions=data.get("open_questions", []),
        transitions=data.get("app_transitions", []),
        model_info={"model": "gpt-4o-mini", "method": "llm"},
    )


def _heuristic_compress(events: List[Event], block_num: int) -> ContextBlock:
    """Deterministic heuristic compression — always available."""
    from core.memory import _infer_goal, _extract_entities, _infer_questions, _build_narrative

    goal = _infer_goal(events)
    entities = _extract_entities(events)
    questions = _infer_questions(events, goal)
    narrative = _build_narrative(events)

    # Derive app transitions
    families = []
    seen = set()
    for e in events:
        fam = e.source_app.app_family
        if fam not in seen:
            families.append(fam)
            seen.add(fam)
    transitions = [f"{families[i]} -> {families[i+1]}" for i in range(len(families) - 1)]

    return _build_block(
        events=events,
        block_num=block_num,
        one_line_goal=goal,
        narrative=narrative,
        entities=entities,
        decisions=[],
        questions=questions,
        transitions=transitions,
        model_info={"method": "heuristic", "version": "1.0"},
    )


def _build_block(
    events: List[Event],
    block_num: int,
    one_line_goal: str,
    narrative: str,
    entities: List[str],
    decisions: List[str],
    questions: List[str],
    transitions: List[str],
    model_info: dict,
) -> ContextBlock:
    seqs = [e.seq for e in events]
    workflow_id = events[0].workflow_id or f"w{block_num:03d}"
    block_id = f"cb_{uuid.uuid4().hex[:8]}"
    toon = encode_events_toon(events)

    block = ContextBlock(
        id=block_id,
        workflow_id=workflow_id,
        event_start=min(seqs),
        event_end=max(seqs),
        event_ids=[e.id for e in events],
        title=f"Context Block {block_num:03d}",
        one_line_goal=one_line_goal,
        narrative=narrative,
        important_entities=entities,
        decisions=decisions,
        open_questions=questions,
        app_transitions=transitions,
        source_hashes=[e.clipboard.payload_hash for e in events],
        created_at=datetime.now(timezone.utc).isoformat(),
        model_info=model_info,
        safety_redactions=[],
        toon_payload=toon,
        markdown_payload="",
    )
    block.markdown_payload = export_events_markdown(events, block)
    return block
