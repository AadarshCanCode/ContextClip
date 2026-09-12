"""
cloud/openrouter.py - shared OpenRouter client helpers.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from core.config import load_env_file


load_env_file()


def openrouter_model(env_name: str = "OPENROUTER_MODEL", default: str = "openai/gpt-4o-mini") -> str:
    return os.environ.get(env_name) or os.environ.get("OPENROUTER_MODEL") or default


def build_openrouter_client(api_key: Optional[str] = None) -> Any:
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY before running OpenRouter actions.")

    from openai import OpenAI

    headers = {}
    site_url = os.environ.get("OPENROUTER_SITE_URL", "https://contextclip.local")
    app_title = os.environ.get("OPENROUTER_APP_TITLE", "ContextClip")
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_title:
        headers["X-Title"] = app_title

    kwargs: dict[str, Any] = {
        "api_key": key,
        "base_url": os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    }
    if headers:
        kwargs["default_headers"] = headers
    return OpenAI(**kwargs)
