"""Wikipedia Tool for The Historical Court.

This module provides async-compatible functions for searching Wikipedia
using LangChain's WikipediaQueryRun wrapped by ADK's LangchainTool.
"""

from __future__ import annotations

import asyncio
import logging
import re
import os
from typing import Any, List, Dict, Optional

from google.adk.tools.langchain_tool import LangchainTool
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = int(os.getenv('WIKI_TOP_K', '5'))
_MAX_TOP_K = 5
_DEFAULT_DOC_CHARS_MAX = 3000

EXCLUSION_PATTERNS = [
    r'\(film\)',
    r'\(movie\)',
    r'\(book\)',
    r'\(novel\)',
    r'\(TV series\)',
    r'\(soap opera\)',
    r'\(fictional character\)',
    r'\(comics\)',
    r'\(band\)',
    r'\(documentary\)',
    r'\(album\)',
    r'\(song\)',
    r'\(video game\)',
    r'\(disambiguation\)',
    r'\(play\)',
    r'\(musical\)',
    r'criticism of (?!.*{topic})',
    r'controversies (?!.*{topic})',
]


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
        return max(200, min(int(raw), 40000))
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


def _parse_wiki_results(output: str) -> List[Dict[str, str]]:
    if not output:
        return []
    pattern = re.compile(r"(?:^|\n)Page: (.*?)\nSummary: (.*?)(?=\nPage: |\Z)", re.S)
    matches = pattern.findall(output)
    return [{'title': m[0].strip(), 'summary': m[1].strip()} for m in matches]


def _truncate_to_sentence(text: str, max_length: int) -> str:
    """Truncate text to the last complete sentence within max_length."""
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    # Find the last sentence ending punctuation
    last_period = truncated.rfind('.')
    last_exclaim = truncated.rfind('!')
    last_question = truncated.rfind('?')
    
    cutoff = max(last_period, last_exclaim, last_question)
    
    if cutoff > 0:
        return truncated[:cutoff+1]
        
    # Fallback if no punctuation found (unlikely for normal text)
    return truncated.rsplit(' ', 1)[0] + "..."

def _format_wiki_results(results: List[Dict[str, str]]) -> str:
    if not results:
        return ""
    
    formatted = []
    for r in results:
        summary = _truncate_to_sentence(r['summary'], _DEFAULT_DOC_CHARS_MAX)
        formatted.append(f"Page: {r['title']}\nSummary: {summary}")
        
    return "\n\n".join(formatted)


def _is_entertainment_page(summary: str) -> bool:
    """Detect if a Wikipedia page is about entertainment media rather than the subject."""
    entertainment_indicators = [
        'is a film',
        'is a movie',
        'is a documentary',
        'is a book written',
        'is a biography written',
        'is a song by',
        'is an album by',
        'is a television series',
        'is a play',
        'is a musical',
        'directed by',
        'starring',
        'was released on',  # for media releases
        'nba', # Sports teams often have "criticism" sections that get picked up
        'basketball',
        'twitter', # Social media platforms often have "criticism" sections
        'facebook',
    ]
    summary_lower = summary.lower()
    return any(indicator in summary_lower for indicator in entertainment_indicators)


def _filter_results_by_phrase(results: List[Dict[str, str]], phrase: str) -> List[Dict[str, str]]:
    if not results or not phrase:
        return results

    phrase_l = phrase.lower()
    # Matches original logic: check only title
    filtered = [r for r in results if phrase_l in (r['title'] or "").lower()]
    return filtered


def _tokenize_focus_term(term: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", term or "")
    tokens = [t.lower() for t in tokens if len(t) > 2]
    return tokens


def _matches_exclusion(pattern: str, title: str, focus_term: str | None = None) -> re.Match | None:
    # Format pattern with focus term if needed (e.g. for "criticism of {topic}")
    try:
        # Escape the focus term to prevent regex injection (e.g. "C++")
        safe_topic = re.escape(focus_term) if focus_term else ""
        formatted_pattern = pattern.format(topic=safe_topic)
        return re.search(formatted_pattern, title, re.IGNORECASE)
    except Exception:
        # Fallback to raw pattern or ignore if invalid regex
        try:
            return re.search(pattern, title, re.IGNORECASE)
        except Exception:
            return None


def _filter_results_by_focus_term(results: List[Dict[str, str]], focus_term: str) -> List[Dict[str, str]]:
    """Filter results to exclude media/entertainment pages and keep relevant ones."""
    if not results or not focus_term:
        return results

    filtered = []
    tokens = _tokenize_focus_term(focus_term)
    if not tokens:
        return results

    def match(text: str) -> bool:
        text_l = (text or "").lower()
        if len(tokens) == 1:
            return tokens[0] in text_l
        return all(t in text_l for t in tokens)

    # Check for matches, prioritizing existing logic but adding exclusions
    for result in results:
        title = result.get('title', '')
        summary = result.get('summary', '')

        # Skip if title matches exclusion patterns
        if any(_matches_exclusion(pattern, title, focus_term) for pattern in EXCLUSION_PATTERNS):
            logger.info(f"Filtered out exclusion pattern: {title}")
            continue
            
        # Relevance Check: Ensure the focus term appears prominently
        # If the focus term is not in the title, it MUST be in the summary
        # And if it's only in the summary, we want to be careful about false positives
        
        title_match = match(title)
        summary_match = match(summary)

        if title_match:
            filtered.append(result)
        elif summary_match:
            # If only in summary, ensure it's not a passing mention?
            # For now, accept it but maybe we can be stricter later if needed
            filtered.append(result)
        else:
            logger.debug(f"Filtered out focus term mismatch: {title}")

    return filtered


async def search_and_summarize(query: str, max_articles: int | None = None, focus_term: str | None = None) -> str:
    """Search Wikipedia and return combined summaries.

    Args:
        query: Search query string
        max_articles: Maximum number of articles to summarize (default None, uses env WIKI_TOP_K or 5)

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

    results = _parse_wiki_results(output)
    
    phrase = _extract_quoted_phrase(q)
    if phrase:
        results = _filter_results_by_phrase(results, phrase)
        
    if focus_term:
        # First filter by focus term and exclusion patterns
        filtered_results = _filter_results_by_focus_term(results, focus_term)
        
        # Then filter by content type (entertainment detection)
        filtered_results = [r for r in filtered_results if not _is_entertainment_page(r.get('summary', ''))]
        
        if not filtered_results and results:
            # Fallback: use the most relevant unfiltered result if it mentions topic
            # BUT must still respect exclusion patterns to avoid "Steve Jobs (film)" when we want "Steve Jobs"
            logger.info(f"No results after filtering for '{focus_term}'. Attempting fallback.")
            for r in results:
                title = r.get('title', '')
                # Re-check exclusion patterns for safety
                if any(_matches_exclusion(pattern, title, focus_term) for pattern in EXCLUSION_PATTERNS):
                    continue
                    
                if focus_term.lower() in title.lower():
                    filtered_results = [r]
                    logger.info(f"Fallback selected: {r['title']}")
                    break
        
        results = filtered_results

    if not results:
        return f"No Wikipedia summaries available for: {q}"

    return _format_wiki_results(results)


def get_search_tool_definition(*, max_results: int | None = None) -> LangchainTool:
    """Returns the LangChain Wikipedia tool wrapped for ADK usage."""

    return _build_langchain_wikipedia_tool(max_results=max_results)
