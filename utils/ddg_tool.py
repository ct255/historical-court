"""DuckDuckGo search tool for finding alternative sources."""
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

async def search_ddg(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search DuckDuckGo for relevant results.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        
    Returns:
        List of dicts with 'title', 'snippet', 'url' keys
    """
    # Use DuckDuckGo HTML search (ddg-api or direct)
    try:
        # Try importing from ddgs first (new package name)
        try:
            from ddgs import DDGS
        except ImportError:
            # Fallback to old package name
            from duckduckgo_search import DDGS
        
        results = []
        # DDGS is synchronous but fast enough for this use case, or we could run in executor if needed.
        # Ideally we should run this in a thread if it blocks, but for now we follow the simple implementation.
        with DDGS() as ddgs:
            # ddgs.text returns an iterator/generator
            ddg_gen = ddgs.text(query, max_results=max_results)
            if ddg_gen:
                for r in ddg_gen:
                    title = r.get('title', '')
                    snippet = r.get('body', '')
                    url = r.get('href', '')
                    
                    # Basic validation: ensure we have meaningful content
                    if not title or not snippet:
                        continue
                        
                    # Filter out results with suspicious dates (e.g., future dates or obviously wrong parsing)
                    # This is a heuristic; deeper date parsing would be better but expensive
                    # For now, we trust the search engine mostly but could filter if snippet starts with future year
                    
                    # Trusted domain boost (optional but good for quality)
                    # We don't discard others, just a note that we accept them
                    
                    results.append({
                        'title': title,
                        'snippet': snippet,
                        'url': url,
                    })
        return results
    except ImportError:
        logger.warning("ddgs/duckduckgo-search not installed, DDG search unavailable")
        return []
    except Exception as e:
        logger.error(f"DDG search failed: {e}")
        return []
