"""Combined search utility with fallback capabilities."""
import logging
import re
from typing import Dict, Optional, Any, List

from utils.wiki_tool import search_and_summarize

logger = logging.getLogger(__name__)

def _tokenize_relevance(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", text) if len(t) > 3]


async def search_with_fallback(
    query: str,
    topic: str,
    use_ddg_fallback: bool = True,
    focus_term: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search Wikipedia first, fall back to DuckDuckGo if no results.
    
    Returns combined results with source attribution.
    """
    # Try Wikipedia first
    # search_and_summarize returns a string (summary) or error message.
    # We need to parse or handle the string return from search_and_summarize.
    # Wait, search_and_summarize returns a string.
    # The user snippet says:
    # if wiki_result and wiki_result.get('summary'):
    # This implies search_and_summarize might return a Dict in the user's mind, 
    # BUT looking at utils/wiki_tool.py: 
    # def search_and_summarize(...) -> str:
    # So I need to adapt the logic or the return type of search_and_summarize.
    # The user instruction says: "wiki_result = search_and_summarize(query, topic)"
    # and then checks "wiki_result.get('summary')".
    # This suggests I might need to update search_and_summarize to return a dict OR handle the string.
    # OR the user assumes it returns a dict.
    # existing wiki_tool.py returns a string.
    
    # Let's look at wiki_tool.py again.
    # line 194: async def search_and_summarize(...) -> str:
    # returns "Combined summary text..." or "No Wikipedia summaries..."
    
    # I should probably wrap the string result into the dict structure expected by the user's logic,
    # OR change the logic to handle the string.
    
    # If I follow the user's snippet exactly, it will break because search_and_summarize returns str.
    # I will adapt the logic to handle the string return from wiki_tool.
    
    wiki_text = await search_and_summarize(query, focus_term=focus_term)
    
    # Check if wiki_text indicates failure
    is_wiki_failure = (
        not wiki_text 
        or wiki_text.lower().startswith("no wikipedia") 
        or wiki_text.lower().startswith("wikipedia error")
        or "no good wikipedia search result" in wiki_text.lower()
    )
    
    if not is_wiki_failure:
        return {
            'title': f"Wikipedia results for {query}", # Placeholder title as we get combined summaries
            'summary': wiki_text,
            'url': 'https://wikipedia.org', # Generic URL since we might have multiple
            'source': 'wikipedia'
        }
    
    # Fallback to DuckDuckGo
    if use_ddg_fallback:
        logger.info(f"Wikipedia search failed for '{query}', falling back to DuckDuckGo")
        from utils.ddg_tool import search_ddg
        # Construct a search query that includes the topic
        ddg_query = f"{topic} {query}" if topic not in query else query
        ddg_results = await search_ddg(ddg_query)
        
        if ddg_results:
            # Filter DDG results for relevance
            relevant_results = []
            relevance_seed = focus_term if focus_term is not None else (query or topic)
            relevance_words = _tokenize_relevance(relevance_seed)
            if not relevance_words:
                relevance_words = _tokenize_relevance(topic)

            for res in ddg_results:
                # Filter out obvious low-quality pages like tags/categories
                if "/tag/" in res['url'] or "/category/" in res['url']:
                    continue

                # Basic check: Topic keywords must appear in title or snippet
                text_to_check = (res['title'] + " " + res['snippet']).lower()
                # At least one significant relevance word should be present
                # Require at least 2 matching tokens for stricter relevance, or 1 if we only have 1 token
                min_matches = 2 if len(relevance_words) > 1 else 1
                
                # Boost strictness: if we have multiple words, require them to appear in the SNIPPET too?
                # Or just rely on the token count. The "BlogOKC" result had "Steve Jobs" in title.
                # Adding the URL filter above should catch the specific reported issue.
                
                if sum(1 for w in relevance_words if w in text_to_check) >= min_matches:
                    relevant_results.append(res)
            
            if relevant_results:
                # Return the most relevant DDG result
                best = relevant_results[0]
                return {
                    'title': best['title'],
                    'summary': best['snippet'],
                    'url': best['url'],
                    'source': 'duckduckgo'
                }
            
    return {
        'title': 'No results',
        'summary': f"No information found for {query} via Wikipedia" + (" or DuckDuckGo" if use_ddg_fallback else ""),
        'url': '',
        'source': 'none'
    }
