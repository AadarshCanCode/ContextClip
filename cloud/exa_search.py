"""
cloud/exa_search.py - Exa-powered reference search for clipboard contents.

This module is an on-demand cloud boundary. It reads or receives clipboard
text, applies the local privacy gate, and sends a compact query to Exa Search
with highlights enabled for token-efficient reference discovery.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from core.config import get_int, load_env_file
from core.privacy import detect_privacy_class, normalize_text
from core.contracts import PrivacyClass


load_env_file()


DEFAULT_SEARCH_TYPE = os.environ.get("EXA_SEARCH_TYPE", "auto")
DEFAULT_NUM_RESULTS = get_int("EXA_NUM_RESULTS", 10)
MAX_QUERY_CHARS = 1000
VALID_SEARCH_TYPES = {
    "auto",
    "fast",
    "instant",
    "deep-lite",
    "deep",
    "deep-reasoning",
}


class ExaSearchError(RuntimeError):
    """Raised when clipboard reference search cannot be performed."""


@dataclass
class ExaReferenceResult:
    title: str
    url: str
    highlights: List[str] = field(default_factory=list)
    author: str = ""
    published_date: str = ""
    score: Optional[float] = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "highlights": self.highlights,
            "author": self.author,
            "published_date": self.published_date,
            "score": self.score,
            "summary": self.summary,
        }


@dataclass
class ClipboardReferenceSearch:
    query: str
    search_type: str
    num_results: int
    results: List[ExaReferenceResult]
    cost_dollars: Optional[float] = None
    source: str = "exa"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "search_type": self.search_type,
            "num_results": self.num_results,
            "source": self.source,
            "cost_dollars": self.cost_dollars,
            "results": [result.to_dict() for result in self.results],
        }


class ExaReferenceSearch:
    """Search web references for clipboard text through Exa."""

    def __init__(self, api_key: Optional[str] = None, client: Any = None) -> None:
        self._api_key = api_key or os.environ.get("EXA_API_KEY")
        self._client = client or self._build_client()

    def _build_client(self) -> Any:
        if not self._api_key:
            raise ExaSearchError("Set EXA_API_KEY before searching clipboard references.")
        try:
            from exa_py import Exa
        except ImportError as exc:
            raise ExaSearchError("Install exa-py to use Exa clipboard reference search.") from exc
        return Exa(api_key=self._api_key)

    def search_text(
        self,
        text: str,
        search_type: str = DEFAULT_SEARCH_TYPE,
        num_results: int = DEFAULT_NUM_RESULTS,
        include_domains: Optional[Iterable[str]] = None,
        exclude_domains: Optional[Iterable[str]] = None,
        max_age_hours: Optional[int] = None,
    ) -> ClipboardReferenceSearch:
        if search_type not in VALID_SEARCH_TYPES:
            valid = ", ".join(sorted(VALID_SEARCH_TYPES))
            raise ExaSearchError(f"Invalid Exa search type '{search_type}'. Use one of: {valid}.")
        if num_results < 1 or num_results > 100:
            raise ExaSearchError("num_results must be between 1 and 100.")

        if detect_privacy_class(text) == PrivacyClass.RESTRICTED:
            raise ExaSearchError("Restricted clipboard content is blocked from Exa search.")

        query = _query_from_clipboard_text(text)
        if not query:
            raise ExaSearchError("Clipboard is empty; nothing to search.")

        contents: dict[str, Any] = {"highlights": True}
        if max_age_hours is not None:
            contents["max_age_hours"] = max_age_hours

        kwargs: dict[str, Any] = {
            "type": search_type,
            "num_results": num_results,
            "contents": contents,
        }
        if include_domains:
            kwargs["include_domains"] = list(include_domains)
        if exclude_domains:
            kwargs["exclude_domains"] = list(exclude_domains)

        response = self._client.search(query, **kwargs)
        results = [_normalize_result(result) for result in (_get(response, "results", []) or [])]
        return ClipboardReferenceSearch(
            query=query,
            search_type=search_type,
            num_results=num_results,
            results=results,
            cost_dollars=_response_cost(response),
        )


def search_clipboard_references(
    text: Optional[str] = None,
    search_type: str = DEFAULT_SEARCH_TYPE,
    num_results: int = DEFAULT_NUM_RESULTS,
    include_domains: Optional[Iterable[str]] = None,
    exclude_domains: Optional[Iterable[str]] = None,
    max_age_hours: Optional[int] = None,
    api_key: Optional[str] = None,
    client: Any = None,
) -> ClipboardReferenceSearch:
    """Search references for the current clipboard text or supplied text."""
    if text is None:
        from core.capture import read_clipboard

        text = read_clipboard()
    return ExaReferenceSearch(api_key=api_key, client=client).search_text(
        text=text,
        search_type=search_type,
        num_results=num_results,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        max_age_hours=max_age_hours,
    )


def _query_from_clipboard_text(text: str) -> str:
    query = normalize_text(text)
    return query[:MAX_QUERY_CHARS].strip()


def _normalize_result(result: Any) -> ExaReferenceResult:
    highlights = _get(result, "highlights", []) or []
    if isinstance(highlights, str):
        highlights = [highlights]
    return ExaReferenceResult(
        title=str(_get(result, "title", "") or ""),
        url=str(_get(result, "url", "") or ""),
        highlights=[str(item) for item in highlights],
        author=str(_get(result, "author", "") or ""),
        published_date=str(_get(result, "published_date", _get(result, "publishedDate", "")) or ""),
        score=_get(result, "score", None),
        summary=str(_get(result, "summary", "") or ""),
    )


def _response_cost(response: Any) -> Optional[float]:
    cost = _get(response, "cost_dollars", None) or _get(response, "costDollars", None)
    total = _get(cost, "total", None) if cost is not None else None
    try:
        return float(total) if total is not None else None
    except (TypeError, ValueError):
        return None


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
