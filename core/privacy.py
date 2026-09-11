"""
core/privacy.py — Content classification, privacy policy, and app exclusion.

Sensitive patterns are detected before cloud upload. Excluded apps
generate no clipboard or screenshot events at all.
"""

from __future__ import annotations

import re
from typing import List, Set

from core.contracts import ContentType, PrivacyClass


# ---------------------------------------------------------------------------
# Content classifier
# ---------------------------------------------------------------------------

_ERROR_RE = re.compile(
    r"(ERR_[A-Z_]+|Exception|Traceback|connection refused|stack trace|ECONNREFUSED|ENOENT|ETIMEDOUT)",
    re.I,
)
_SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", re.I)
_URL_RE = re.compile(r"^https?://", re.I)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_DATE_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.I,
)
_CODE_STMT_RE = re.compile(
    r"(^|\n)\s*(def |class |function |import |from |const |let |var |public |private |#include|package )",
)
_CODE_STRUCT_RE = re.compile(r"[{}\[\]();=]")


def classify_content(text: str) -> str:
    """Deterministic content-type classifier."""
    s = text.strip()
    if not s:
        return ContentType.EMPTY.value
    if _ERROR_RE.search(s):
        return ContentType.ERROR.value
    if _SQL_RE.search(s):
        return ContentType.SQL.value
    if _URL_RE.search(s):
        return ContentType.URL.value
    if _EMAIL_RE.search(s):
        return ContentType.EMAIL.value
    if _DATE_RE.search(s):
        return ContentType.EVENT_OR_DATE.value
    if _CODE_STMT_RE.search(s):
        return ContentType.CODE.value
    if len(s.splitlines()) > 3 and _CODE_STRUCT_RE.search(s):
        return ContentType.CODE_OR_CONFIG.value
    return ContentType.TEXT.value


# ---------------------------------------------------------------------------
# Sensitive pattern detector
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"\b(password|passwd|secret|api.?key|token|bearer|private.?key)\s*[=:]\s*\S+", re.I),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),   # base64-like secrets
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # credit card-like
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like
    re.compile(r"ghp_[A-Za-z0-9]{36}"),    # GitHub PAT
    re.compile(r"sk-[A-Za-z0-9]{48}"),     # OpenAI key
]


def detect_privacy_class(text: str) -> PrivacyClass:
    """Classify the privacy sensitivity of clipboard text."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            return PrivacyClass.RESTRICTED
    return PrivacyClass.PUBLIC


# ---------------------------------------------------------------------------
# App exclusion list
# ---------------------------------------------------------------------------

# Default excluded app families (password managers, banking, etc.)
_DEFAULT_EXCLUDED_FAMILIES: Set[str] = {
    "keepass",
    "1password",
    "bitwarden",
    "lastpass",
}

# Default excluded process name patterns
_DEFAULT_EXCLUDED_PROCESSES: List[re.Pattern] = [
    re.compile(r"keepass", re.I),
    re.compile(r"1password", re.I),
    re.compile(r"bitwarden", re.I),
    re.compile(r"lockwatcher", re.I),
]


class AppExclusionPolicy:
    """
    Determines whether a given app/window should be excluded from capture.
    Excluded apps generate no clipboard or screenshot events.
    """

    def __init__(
        self,
        extra_families: List[str] | None = None,
        extra_patterns: List[str] | None = None,
    ) -> None:
        self._families = set(_DEFAULT_EXCLUDED_FAMILIES)
        if extra_families:
            self._families.update(f.lower() for f in extra_families)

        self._patterns = list(_DEFAULT_EXCLUDED_PROCESSES)
        if extra_patterns:
            for p in extra_patterns:
                self._patterns.append(re.compile(p, re.I))

    def is_excluded(self, app_family: str, process_name: str, window_title: str) -> bool:
        if app_family.lower() in self._families:
            return True
        combined = f"{process_name} {window_title}".lower()
        return any(p.search(combined) for p in self._patterns)


# ---------------------------------------------------------------------------
# Safe preview helper
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip()


def safe_preview(text: str, n: int = 240) -> str:
    t = normalize_text(text)
    return t if len(t) <= n else t[: n - 1] + "…"
