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
    """Extract tool output for a named tool.

    Supports both:
    - function_response (tool was executed by the runner)
    - function_call (model requested the tool call; runner may not have executed it)

    Returns:
        - dict of parsed tool payload (preferred)
        - {} if a matching tool part is found but has no usable payload
        - None if no matching tool part is found
    """

    name = (tool_name or "").strip()
    if not name:
        return None

    def _coerce_args(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {"args": parsed}
            except Exception:
                return {"args": value}
        return {"args": value}

    for part in iter_parts(events):
        # Case 1: tool response (runner executed tool)
        fr = _get_attr(part, "function_response")
        if fr:
            fr_name = _get_attr(fr, "name")
            if fr_name != name:
                continue

            args = _coerce_args(_get_attr(fr, "args")) or {}
            result = args.get("result") if isinstance(args, dict) else None

            # Most ADK tool responses place tool return under args.result
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

        # Case 2: tool call request (runner did not execute tool; still treat as a usable "result")
        fc = _get_attr(part, "function_call")
        if fc:
            fc_name = _get_attr(fc, "name")
            if fc_name != name:
                continue

            args = _coerce_args(_get_attr(fc, "args"))
            return args or {}

    return None
