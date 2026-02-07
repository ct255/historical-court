from __future__ import annotations

import os
from typing import Iterable

from dotenv import load_dotenv


def load_environment() -> None:
    """Load environment variables from .env if present."""
    load_dotenv()


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def require_env(name: str) -> str:
    value = get_env(name)
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


def require_any_env(names: Iterable[str]) -> str:
    for name in names:
        value = get_env(name)
        if value:
            return value
    raise ValueError("Missing required env vars: " + ", ".join(names))


def get_model_name(default: str = "gemini-2.5-flash") -> str:
    model = get_env("MODEL", default)
    if not model:
        return default
    return model
