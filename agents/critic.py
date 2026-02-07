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
            return "controversy scandal failure casualties criticism fraud corruption defeat opposition"

        base = f"\"{t}\" controversy scandal failure casualties criticism fraud corruption defeat opposition"
        f = re.sub(r"\s+", " ", (feedback or "").strip())
        if not f:
            return base

        f_short = " ".join(f.split(" ")[:12]).strip()
        return f"{base} {f_short}".strip()

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

    async def generate_search_query(self, topic: str, feedback: str = "") -> str:
        """Generate a critical search query for the given topic.

        Args:
            topic: The subject to research
            feedback: Optional feedback from the Judge for refinement

        Returns:
            A search query string focused on negative/controversial aspects
        """

        t = (topic or "").strip()
        if not t:
            return self._fallback_query(topic, feedback)

        fb = (feedback or "").strip()
        prompt = (
            "Generate a CRITICAL/NEGATIVE Wikipedia search query.\n"
            f"TOPIC: {t}\n"
            f"FEEDBACK: {fb if fb else 'None'}\n"
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

                if t and t.lower() not in query.lower():
                    query = f"\"{t}\" {query}".strip()

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

    async def research(self, topic: str, feedback: str = "") -> str:
        """Complete research cycle: generate query, search Wikipedia, return findings.

        Args:
            topic: The subject to research
            feedback: Optional feedback from the Judge for refinement

        Returns:
            String containing the critical findings from Wikipedia
        """
        query, findings = await self.research_with_query(topic, feedback)
        return findings

    async def research_with_query(self, topic: str, feedback: str = "") -> tuple[str, str]:
        """Complete research cycle and return both query and findings.

        Returns:
            Tuple of (query, findings)
        """

        t = (topic or "").strip()
        if not t:
            return "", "No topic provided."

        query = await self.generate_search_query(t, feedback)

        try:
            findings = await search_and_summarize(query, max_articles=2, focus_term=t)
        except Exception as e:
            logger.exception("Wikipedia research failed", extra={"topic": t, "query": query, "error": str(e)})
            return query, f"Wikipedia research error for query: {query}"

        findings = (findings or "").strip()
        if not findings or findings.lower().startswith("no wikipedia"):
            logger.info("No Wikipedia results for critic query", extra={"topic": t, "query": query})
            return query, f"No critical Wikipedia evidence found for: {t}"

        logger.debug("Critic research completed", extra={"topic": t, "query": query, "chars": len(findings)})
        return query, findings
