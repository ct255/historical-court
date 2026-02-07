
import re
import logging
from typing import List, Dict

# --- Mocks/Copies from utils/wiki_tool.py ---

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

def _tokenize_focus_term(term: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", term or "")
    tokens = [t.lower() for t in tokens if len(t) > 2]
    return tokens

def _is_entertainment_page(summary: str) -> bool:
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
        'was released on',
    ]
    summary_lower = summary.lower()
    return any(indicator in summary_lower for indicator in entertainment_indicators)

def _filter_results_by_focus_term(results: List[Dict[str, str]], focus_term: str) -> List[Dict[str, str]]:
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

    for result in results:
        title = result.get('title', '')
        summary = result.get('summary', '')

        def _matches_exclusion(pattern, title):
            try:
                safe_topic = re.escape(focus_term) if focus_term else ""
                formatted_pattern = pattern.format(topic=safe_topic)
                return re.search(formatted_pattern, title, re.IGNORECASE)
            except Exception:
                try:
                    return re.search(pattern, title, re.IGNORECASE)
                except Exception:
                    return None

        if any(_matches_exclusion(pattern, title) for pattern in EXCLUSION_PATTERNS):
            print(f"Filtered out exclusion pattern: {title}")
            continue
            
        title_match = match(title)
        summary_match = match(summary)

        if title_match:
            filtered.append(result)
        elif summary_match:
            filtered.append(result)

    return filtered

def test_wiki_fallback():
    print("--- Test Wiki Fallback ---")
    results = [
        {'title': 'Steve Jobs (film)', 'summary': 'Steve Jobs is a 2015 biographical drama film...'},
        {'title': 'Steve Jobs', 'summary': 'Steven Paul Jobs was an American businessman...'} 
    ]
    # Let's assume the "Steve Jobs" page was NOT returned or was filtered out for some reason (e.g. maybe it didn't match some other criteria in a real run, or maybe the search engine returned ONLY the film page due to query "Steve Jobs controversy").
    # Scenario: Search returned only the film page.
    results_only_film = [
        {'title': 'Steve Jobs (film)', 'summary': 'Steve Jobs is a 2015 biographical drama film...'}
    ]
    
    focus_term = "Steve Jobs"
    
    # 1. First filter by focus term and exclusion patterns
    filtered_results = _filter_results_by_focus_term(results_only_film, focus_term)
    print(f"After initial filter: {[r['title'] for r in filtered_results]}")
    
    # 2. Then filter by content type (entertainment detection)
    filtered_results = [r for r in filtered_results if not _is_entertainment_page(r.get('summary', ''))]
    print(f"After entertainment filter: {[r['title'] for r in filtered_results]}")

    # 3. Fallback Logic (copied from utils/wiki_tool.py lines 291-298)
    if not filtered_results and results_only_film:
        print("Triggering Fallback Logic...")
        for r in results_only_film:
            if focus_term.lower() in r.get('title', '').lower():
                filtered_results = [r]
                print(f"Fallback selected: {r['title']}")
                break
    
    print(f"Final Results: {[r['title'] for r in filtered_results]}")

# --- Mocks/Copies from utils/search.py ---

def _tokenize_relevance(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", text) if len(t) > 3]

def test_ddg_relevance():
    print("\n--- Test DDG Relevance ---")
    query = "Steve Jobs controversy"
    topic = "Steve Jobs"
    focus_term = "Steve Jobs"
    
    res = {
        'title': "Steve Jobs – Jim Stafford's BlogOKC",
        'snippet': "The author of the Power On newsletter , Gurman had already detailed almost everything Apple debuted, down to the specs of the iPhone Air and cameras ...",
        'url': "https://jim-stafford.com/tag/steve-jobs/"
    }
    
    relevance_seed = focus_term if focus_term is not None else (query or topic)
    relevance_words = _tokenize_relevance(relevance_seed)
    print(f"Relevance words: {relevance_words}")
    
    if not relevance_words:
        relevance_words = _tokenize_relevance(topic)

    # Basic check: Topic keywords must appear in title or snippet
    text_to_check = (res['title'] + " " + res['snippet']).lower()
    
    min_matches = 2 if len(relevance_words) > 1 else 1
    match_count = sum(1 for w in relevance_words if w in text_to_check)
    
    print(f"Text to check: {text_to_check}")
    print(f"Match count: {match_count}")
    print(f"Min matches: {min_matches}")
    
    if match_count >= min_matches:
        print("Result ACCEPTED")
    else:
        print("Result REJECTED")

if __name__ == "__main__":
    test_wiki_fallback()
    test_ddg_relevance()
