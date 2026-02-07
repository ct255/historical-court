"""Agent B: The Critic - A cynical historian focusing on controversies and failures.

This agent generates critical search queries and gathers negative/controversial
evidence about historical figures/events using Wikipedia.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

from google.adk import Agent
from google.adk.runners import InMemoryRunner

from utils.adk_helpers import extract_text
from utils.wiki_tool import search_and_summarize
from utils.search import search_with_fallback

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """You are The Critic, a cynical historian who scrutinizes historical figures and events with a critical eye.

Your Role:
- Focus on controversies, failures, and negative impacts
- Highlight casualties, economic losses, and moral failures
- Expose scandals, frauds, and questionable decisions
- Challenge the popular narrative with uncomfortable truths

Your Task:
Given a topic and optional feedback from the Judge, generate a search query that will find CRITICAL/NEGATIVE information.

Guidelines for Query Generation:
- Use keywords like: controversy, scandal, failure, casualties, criticism, massacre, fraud, corruption, defeat, opposition
- If feedback is provided, refine your search based on the Judge's instructions
- Be specific but comprehensive - target documented criticisms

Output Format:
Return ONLY the search query, nothing else. No explanations, no formatting.
"""


class CriticAgent:
    """The Critic agent that researches negative/controversial aspects of topics.

    Attributes:
        provider: The LLM provider instance
        config: Configuration for content generation
    """

    def __init__(
        self,
        *,
        model: object = "gemini-2.5-flash",
        app_name: str = "historical-court",
        generate_content_config: object | None = None,
    ):
        self.model = model
        self.app_name = app_name

        self.agent = Agent(
            name="critic",
            model=self.model,
            instruction=CRITIC_SYSTEM_PROMPT,
            description="Critical historian focusing on controversies and failures.",
            generate_content_config=generate_content_config,
        )
        self.runner = InMemoryRunner(agent=self.agent, app_name=self.app_name)
        self.user_id = "critic_user"
        self.session_id = "critic_session"

    def _fallback_query(self, topic: str, feedback: str = "") -> str:
        t = (topic or "").strip()
        if not t:
            return "controversy criticism"

        # Simpler fallback: just topic + 2 key terms
        return f"{t} controversy criticism"

    def _sanitize_query(self, query: str) -> str:
        q = (query or "").strip()
        q = re.sub(r"[\r\n]+", " ", q)
        q = q.strip(" \t\"'`“”‘’")
        q = re.sub(r"\s+", " ", q).strip()
        return q

    @staticmethod
    def _is_resource_exhausted(err: Exception) -> bool:
        msg = str(err).upper()
        return "RESOURCE_EXHAUSTED" in msg or "429" in msg

    async def generate_search_query(
        self,
        topic: str,
        feedback: str = "",
        previous_queries: list[str] = None,
        suggested_queries: list[str] = None
    ) -> str:
        """Generate a critical search query for the given topic.

        Args:
            topic: The subject to research
            feedback: Optional feedback from the Judge for refinement
            previous_queries: List of queries already tried to avoid duplicates
            suggested_queries: Optional list of specific queries suggested by Judge

        Returns:
            A search query string focused on negative/controversial aspects
        """

        # Priority 1: Use specific suggestions from the Judge if available
        if suggested_queries:
            # Filter out queries we've already used
            previous_set = set(previous_queries or [])
            valid_suggestions = [q for q in suggested_queries if q not in previous_set]
            
            if valid_suggestions:
                # Use the first valid suggestion
                suggestion = valid_suggestions[0]
                logger.info(f"Critic using judge's suggested query: {suggestion}")
                return suggestion

        t = (topic or "").strip()
        if not t:
            return self._fallback_query(topic, feedback)

        fb = (feedback or "").strip()
        prev_q = (previous_queries or [])
        
        previous_queries_str = ""
        if prev_q:
            previous_queries_str = (
                "\nDO NOT use any of these previously tried queries:\n" +
                "\n".join(f"- {q}" for q in prev_q) +
                "\nGenerate a DIFFERENT query with new search angles."
            )

        prompt = (
            "Generate a TARGETED Wikipedia search query (3-6 keywords) for CONTROVERSIAL/CRITICAL info.\n"
            f"TOPIC: {t}\n"
            f"FEEDBACK: {fb if fb else 'None'}\n"
            f"{previous_queries_str}\n"
            "REQUIREMENTS:\n"
            "1. Focus on specific scandals, criticisms, failures, or negative legacy.\n"
            "2. Combine the topic with terms like: controversy, criticism, scandal, allegations, failure, crimes, dispute.\n"
            "3. Example: instead of just 'Steve Jobs', use 'Steve Jobs criticism' or 'Steve Jobs antitrust'.\n"
            "4. Do NOT use quotes or complex operators."
        )

        max_attempts = int(os.environ.get("ADK_QUERY_RETRIES", "3") or "3")
        base_delay = float(os.environ.get("ADK_QUERY_RETRY_BASE_SECONDS", "1.5") or "1.5")

        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                events = await self.runner.run_debug(
                    prompt,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    quiet=True,
                )
                query = self._sanitize_query(extract_text(events) or "")

                # Ensure topic is present, but avoid double quoting if possible
                if t and t.lower() not in query.lower():
                    # If the query is very short, just append it
                    query = f"{t} {query}".strip()

                if not query:
                    logger.info("Critic returned empty query; using fallback", extra={"topic": t})
                    return self._fallback_query(topic, feedback)

                logger.debug("Critic generated search query", extra={"topic": t, "query": query})
                return query

            except Exception as e:
                last_error = e
                if self._is_resource_exhausted(e) and attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                break

        logger.info(
            "Critic failed to generate search query; using fallback",
            extra={"topic": t, "error": str(last_error) if last_error else ""},
        )
        return self._fallback_query(topic, feedback)

    async def research(self, topic: str, feedback: str = "", previous_queries: list[str] = None, suggested_queries: list[str] = None) -> str:
        """Complete research cycle: generate query, search Wikipedia, return findings.

        Args:
            topic: The subject to research
            feedback: Optional feedback from the Judge for refinement
            previous_queries: List of queries already tried to avoid duplicates
            suggested_queries: Optional list of specific queries suggested by Judge

        Returns:
            String containing the critical findings from Wikipedia
        """
        query, findings = await self.research_with_query(topic, feedback, previous_queries, suggested_queries)
        return findings

    async def research_with_query(
        self,
        topic: str,
        feedback: str = "",
        previous_queries: list[str] = None,
        suggested_queries: list[str] = None
    ) -> tuple[str, str]:
        """Complete research cycle and return both query and findings.

        Returns:
            Tuple of (query, findings)
        """

        t = (topic or "").strip()
        if not t:
            return "", "No topic provided."

        query = await self.generate_search_query(t, feedback, previous_queries, suggested_queries)

        findings = ""
        def _is_generic_topic_page(text: str, topic_name: str) -> bool:
            if not text:
                return False
            titles = re.findall(r"^Page:\s*(.+)$", text, flags=re.MULTILINE)
            if not titles:
                return False
            titles_norm = [t.strip().lower() for t in titles if t.strip()]
            topic_norm = topic_name.strip().lower()
            if not topic_norm:
                return False
            return len(titles_norm) == 1 and titles_norm[0] == topic_norm

        try:
            # Use search_with_fallback which tries Wikipedia then DuckDuckGo
            search_result = await search_with_fallback(
                query=query,
                topic=t,
                use_ddg_fallback=True,
                focus_term=t,
            )
            
            findings = search_result.get('summary', '')
            source = search_result.get('source', 'unknown')
            
            if source == 'duckduckgo':
                # Add attribution for DDG results
                title = search_result.get('title', 'Unknown Source')
                url = search_result.get('url', '')
                findings = f"[Source: DuckDuckGo - {title}]({url})\n\n{findings}"
            elif source == 'wikipedia' and _is_generic_topic_page(findings, t):
                logger.info("Generic topic page returned; broadening search", extra={"topic": t, "query": query})
                broadened = await search_with_fallback(
                    query=query,
                    topic=t,
                    use_ddg_fallback=True,
                    focus_term=t,
                )
                broadened_findings = broadened.get('summary', '')
                broadened_source = broadened.get('source', 'unknown')
                if broadened_source == 'duckduckgo':
                    title = broadened.get('title', 'Unknown Source')
                    url = broadened.get('url', '')
                    broadened_findings = f"[Source: DuckDuckGo - {title}]({url})\n\n{broadened_findings}"
                if broadened_findings:
                    findings = broadened_findings
                
        except Exception as e:
            logger.warning(f"Research failed for primary query '{query}': {e}")
            findings = ""

        # Check if we got valid results
        findings = (findings or "").strip()
        is_failure = (
            not findings
            or findings.lower().startswith("no information found")
            or findings.lower().startswith("no wikipedia")
        )

        if is_failure:
            logger.info("No results for primary query, trying fallback", extra={"topic": t, "query": query})
            
            # Simple fallback query
            fallback_query = f"{t} controversy criticism"
            try:
                search_result = await search_with_fallback(
                    query=fallback_query,
                    topic=t,
                    use_ddg_fallback=True,
                    focus_term=None,
                )
                findings = search_result.get('summary', '')
                source = search_result.get('source', 'unknown')
                
                if source == 'duckduckgo':
                    title = search_result.get('title', 'Unknown Source')
                    url = search_result.get('url', '')
                    findings = f"[Source: DuckDuckGo - {title}]({url})\n\n{findings}"
                
                if findings and not findings.lower().startswith("no information found"):
                    return fallback_query, findings
            except Exception as e:
                logger.warning(f"Fallback search failed: {e}")

            return query, f"No critical evidence found for: {t}"

        logger.debug("Critic research completed", extra={"topic": t, "query": query, "chars": len(findings)})
        return query, findings
