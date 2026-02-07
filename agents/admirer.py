"""Agent A: The Admirer - A biased historian focusing on achievements.

This agent generates optimistic search queries and gathers positive
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

logger = logging.getLogger(__name__)

ADMIRER_SYSTEM_PROMPT = """You are The Admirer, a passionate historian who sees the best in historical figures and events.

Your Role:
- Focus on achievements, positive contributions, and legacy
- Highlight heroic actions, reforms, and beneficial impacts
- Emphasize cultural, scientific, or social advancements
- Find the silver lining even in controversial figures

Your Task:
Given a topic and optional feedback from the Judge, generate a search query that will find POSITIVE information.

Guidelines for Query Generation:
- Use keywords like: achievements, contributions, legacy, reforms, innovations, victories, accomplishments
- If feedback is provided, refine your search based on the Judge's instructions
- Be specific but comprehensive

Output Format:
Return ONLY the search query, nothing else. No explanations, no formatting.
"""


class AdmirerAgent:
    """The Admirer agent that researches positive aspects of topics.

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
            name="admirer",
            model=self.model,
            instruction=ADMIRER_SYSTEM_PROMPT,
            description="Optimistic historian focusing on achievements and legacy.",
            generate_content_config=generate_content_config,
        )
        self.runner = InMemoryRunner(agent=self.agent, app_name=self.app_name)
        self.user_id = "admirer_user"
        self.session_id = "admirer_session"

    def _fallback_query(self, topic: str, feedback: str = "") -> str:
        t = (topic or "").strip()
        if not t:
            return "legacy achievements"

        # Simpler fallback: just topic + 2 key terms
        return f"{t} legacy achievements"

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
        """Generate an optimistic search query for the given topic.

        Args:
            topic: The subject to research
            feedback: Optional feedback from the Judge for refinement
            previous_queries: List of queries already tried to avoid duplicates
            suggested_queries: Optional list of specific queries suggested by Judge

        Returns:
            A search query string focused on positive aspects
        """

        # Priority 1: Use specific suggestions from the Judge if available
        if suggested_queries:
            # Filter out queries we've already used
            previous_set = set(previous_queries or [])
            valid_suggestions = [q for q in suggested_queries if q not in previous_set]
            
            if valid_suggestions:
                # Use the first valid suggestion
                suggestion = valid_suggestions[0]
                logger.info(f"Admirer using judge's suggested query: {suggestion}")
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
            "Generate a SIMPLE Wikipedia search query (3-5 keywords max).\n"
            f"TOPIC: {t}\n"
            f"FEEDBACK: {fb if fb else 'None'}\n"
            f"{previous_queries_str}\n"
            "Focus on specific positive terms (e.g. 'legacy', 'reforms', 'victory').\n"
            "Do NOT use quotes or complex operators."
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
                    logger.info("Admirer returned empty query; using fallback", extra={"topic": t})
                    return self._fallback_query(topic, feedback)

                logger.debug("Admirer generated search query", extra={"topic": t, "query": query})
                return query

            except Exception as e:
                last_error = e
                if self._is_resource_exhausted(e) and attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                break

        logger.info(
            "Admirer failed to generate search query; using fallback",
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
            String containing the positive findings from Wikipedia
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
        try:
            # max_articles=None will use default from env/config (5)
            findings = await search_and_summarize(query, max_articles=None, focus_term=t)
        except Exception as e:
            logger.warning(f"Wikipedia research failed for primary query '{query}': {e}")
            findings = ""

        # Fallback if primary query failed or returned nothing
        findings = (findings or "").strip()
        if not findings or findings.lower().startswith("no wikipedia"):
            logger.info("No results for primary query, trying fallback", extra={"topic": t, "query": query})
            
            # Simple fallback query
            fallback_query = f"{t} biography legacy"
            try:
                # max_articles=None will use default from env/config (5)
                findings = await search_and_summarize(fallback_query, max_articles=None, focus_term=t)
                if findings and not findings.lower().startswith("no wikipedia"):
                    return fallback_query, findings
            except Exception as e:
                logger.warning(f"Fallback search failed: {e}")

            return query, f"No positive Wikipedia evidence found for: {t}"

        logger.debug("Admirer research completed", extra={"topic": t, "query": query, "chars": len(findings)})
        return query, findings
