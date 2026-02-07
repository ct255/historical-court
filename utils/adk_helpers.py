from __future__ import annotations

import json
from typing import Any, Iterable, Optional


def _get_attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def iter_parts(events: Iterable[Any]) -> Iterable[Any]:
    for event in events or []:
        content = _get_attr(event, "content") or _get_attr(event, "data")
        parts = _get_attr(content, "parts")
        if not parts:
            continue
        for part in parts:
            yield part


def extract_text(events: Iterable[Any]) -> str:
    last_text = ""
    for part in iter_parts(events):
        text = _get_attr(part, "text")
        if text:
            last_text = str(text)
    return (last_text or "").strip()


def extract_tool_result(events: Iterable[Any], tool_name: str) -> Optional[dict[str, Any]]:
    name = (tool_name or "").strip()
    if not name:
        return None

    for part in iter_parts(events):
        fr = _get_attr(part, "function_response")
        if not fr:
            continue

        fr_name = _get_attr(fr, "name")
        if fr_name != name:
            continue

        args = _get_attr(fr, "args") or {}
        result = args.get("result") if isinstance(args, dict) else None

        if result is None:
            return {}

        if isinstance(result, dict):
            return result

        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except Exception:
                return {"result": result}

        return {"result": result}

    return None
