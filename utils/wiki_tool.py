"""Wikipedia Tool for The Historical Court.

This module provides async-compatible functions for searching Wikipedia
using LangChain's WikipediaQueryRun wrapped by ADK's LangchainTool.
"""

from __future__ import annotations

import asyncio
import logging
import re
import os
from typing import Any

from google.adk.tools.langchain_tool import LangchainTool
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 2
_MAX_TOP_K = 5
_DEFAULT_DOC_CHARS_MAX = 1400


def _coerce_top_k(value: int | None) -> int:
    try:
        top_k = int(value) if value is not None else _DEFAULT_TOP_K
    except Exception:
        top_k = _DEFAULT_TOP_K
    return max(1, min(top_k, _MAX_TOP_K))


def _doc_chars_max() -> int:
    raw = (os.getenv("WIKIPEDIA_DOC_CHARS_MAX") or "").strip()
    if not raw:
        return _DEFAULT_DOC_CHARS_MAX
    try:
        return max(200, min(int(raw), 400000))
    except Exception:
        return _DEFAULT_DOC_CHARS_MAX


def _build_langchain_wikipedia_tool(*, max_results: int | None = None) -> LangchainTool:
    top_k = _coerce_top_k(max_results)
    wrapper = WikipediaAPIWrapper(
        top_k_results=top_k,
        doc_content_chars_max=_doc_chars_max(),
        load_all_available_meta=False,
    )
    return LangchainTool(tool=WikipediaQueryRun(api_wrapper=wrapper))


def _build_wikipedia_query_tool(*, max_results: int | None = None) -> WikipediaQueryRun:
    top_k = _coerce_top_k(max_results)
    wrapper = WikipediaAPIWrapper(
        top_k_results=top_k,
        doc_content_chars_max=_doc_chars_max(),
        load_all_available_meta=False,
    )
    return WikipediaQueryRun(api_wrapper=wrapper)


def _invoke_langchain_tool(tool: Any, query: str) -> str:
    inner = (
        getattr(tool, "tool", None)
        or getattr(tool, "langchain_tool", None)
        or getattr(tool, "lc_tool", None)
        or getattr(tool, "_tool", None)
        or tool
    )
    for method in ("invoke", "run"):
        fn = getattr(inner, method, None)
        if callable(fn):
            result = fn(query)
            return result if isinstance(result, str) else str(result)
    if callable(inner):
        result = inner(query)
        return result if isinstance(result, str) else str(result)
    raise RuntimeError("LangChain Wikipedia tool is not callable")


def _extract_quoted_phrase(query: str) -> str | None:
    match = re.search(r"\"([^\"]+)\"", query or "")
    if not match:
        return None
    phrase = (match.group(1) or "").strip()
    return phrase if phrase else None


def _filter_results_by_phrase(output: str, phrase: str) -> str:
    if not output or not phrase:
        return output

    pattern = re.compile(r"(?:^|\n)Page: (.*?)\nSummary: (.*?)(?=\nPage: |\Z)", re.S)
    matches = pattern.findall(output)
    if not matches:
        return output

    phrase_l = phrase.lower()
    filtered = [m for m in matches if phrase_l in (m[0] or "").lower()]
    if not filtered:
        return output

    return "\n\n".join(f"Page: {title}\nSummary: {summary.strip()}" for title, summary in filtered)


def _tokenize_focus_term(term: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", term or "")
    tokens = [t.lower() for t in tokens if len(t) > 2]
    return tokens


def _filter_results_by_focus_term(output: str, focus_term: str) -> str:
    if not output or not focus_term:
        return output

    pattern = re.compile(r"(?:^|\n)Page: (.*?)\nSummary: (.*?)(?=\nPage: |\Z)", re.S)
    matches = pattern.findall(output)
    if not matches:
        return output

    tokens = _tokenize_focus_term(focus_term)
    if not tokens:
        return output

    def title_match(title: str) -> bool:
        title_l = (title or "").lower()
        if len(tokens) == 1:
            return tokens[0] in title_l
        return all(t in title_l for t in tokens)

    def summary_match(summary: str) -> bool:
        summary_l = (summary or "").lower()
        if len(tokens) == 1:
            return tokens[0] in summary_l
        return all(t in summary_l for t in tokens)

    title_filtered = [m for m in matches if title_match(m[0])]
    if title_filtered:
        return "\n\n".join(
            f"Page: {title}\nSummary: {summary.strip()}" for title, summary in title_filtered
        )

    summary_filtered = [m for m in matches if summary_match(m[1])]
    if summary_filtered:
        return "\n\n".join(
            f"Page: {title}\nSummary: {summary.strip()}" for title, summary in summary_filtered
        )

    return ""


async def search_and_summarize(query: str, max_articles: int = 2, focus_term: str | None = None) -> str:
    """Search Wikipedia and return combined summaries.

    Args:
        query: Search query string
        max_articles: Maximum number of articles to summarize (default 2)

    Returns:
        Combined summary text from relevant articles, or error message
    """

    q = (query or "").strip()
    if not q:
        return "No query provided."

    tool = _build_wikipedia_query_tool(max_results=max_articles)

    try:
        result = await asyncio.to_thread(_invoke_langchain_tool, tool, q)
    except Exception as exc:
        logger.exception("Wikipedia tool error", extra={"query": q, "error": str(exc)})
        return f"Wikipedia error: {exc}"

    output = (result or "").strip()
    if "no good wikipedia search result" in output.lower():
        return "No good Wikipedia Search Result was found"

    phrase = _extract_quoted_phrase(q)
    output = _filter_results_by_phrase(output, phrase or "")
    if focus_term:
        output = _filter_results_by_focus_term(output, focus_term)

    if not output:
        return f"No Wikipedia summaries available for: {q}"

    return output


def get_search_tool_definition(*, max_results: int = 3) -> LangchainTool:
    """Returns the LangChain Wikipedia tool wrapped for ADK usage."""

    return _build_langchain_wikipedia_tool(max_results=max_results)
