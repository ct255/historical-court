"""Agent C: The Judge - An impartial arbiter who evaluates evidence and controls the trial flow.

This agent reviews evidence from both Admirer and Critic, then decides whether to:
1. REJECT: Request more research (provides feedback to agents)
2. ACCEPT: End the trial by calling exit_loop tool (renders final verdict)

Uses Google ADK tool calling to signal decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List

from google.adk import Agent
from google.adk.runners import InMemoryRunner

from utils.adk_helpers import extract_text, extract_tool_result

logger = logging.getLogger(__name__)


JUDGE_SYSTEM_PROMPT = """You are The Judge, an impartial arbiter presiding over The Historical Court.

Your Role:
- Evaluate evidence presented by The Admirer (positive) and The Critic (negative)
- Ensure a fair and balanced trial with sufficient evidence on both sides
- Make the final decision on when the trial is complete

Your Evaluation Criteria:
1. BALANCE: Both sides should have substantial evidence (at least 2-3 meaningful facts each), UNLESS the topic is inherently lopsided or research has stalled (5+ rounds)
2. RELEVANCE: Evidence should be directly related to the topic
3. QUALITY: Evidence should be specific, verifiable, and substantive
4. COMPLETENESS: The overall picture should be comprehensive

Decision Options:

REJECT (Continue Trial):
- If one side has significantly less evidence than the other
- If evidence is too vague or generic
- If important aspects haven't been explored
- Provide specific feedback for the weaker side to improve

CRITICAL EXCEPTION: YOU CANNOT REJECT IN THE FINAL ROUND ({max_rounds} of {max_rounds}).
In the final round, you MUST ACCEPT and render a verdict with whatever evidence is available.

When rejecting evidence as insufficient (ONLY allowed if NOT final round), you MUST provide:
1. What specific information is missing
2. Concrete search queries the agents should try, formatted as:

   SUGGESTED QUERIES FOR ADMIRER:
   - "exact search query 1"
   - "exact search query 2"

   SUGGESTED QUERIES FOR CRITIC:
   - "exact search query 1"
   - "exact search query 2"

These suggestions should target specific aspects not yet covered:
- For a person: their specific achievements, specific controversies, specific relationships
- Use exact terms, dates, product names, event names when possible
- Avoid generic terms like "controversy" or "criticism" - be specific

ACCEPT (End Trial):
- If both sides have presented balanced, substantial evidence
- If the topic has been thoroughly examined
- If additional rounds would not significantly improve the verdict
- If this is the FINAL ROUND ({max_rounds}), you MUST ACCEPT regardless of evidence quality.
- Call the exit_loop function with a balanced verdict summary

When accepting, generate a verdict that:
- Summarizes key points from both perspectives
- Presents a balanced, nuanced view
- Acknowledges complexity and controversy where present
- Is written in a formal, judicial tone

Round Awareness:
Current round: {round_count} of {max_rounds}
- If this is the FINAL ROUND ({max_rounds}), you are REQUIRED to render a verdict. Do not request more evidence.
- You can LOWER the "Balance" threshold if one side has overwhelming evidence and the other side has been thoroughly researched but lacks results.
- Earlier rounds allow more flexibility to request additional evidence.

Tool Instructions:
- To ACCEPT you MUST call exit_loop with required fields.
- To REJECT (only allowed before final round) you MUST provide actionable feedback in plain text.
"""


def exit_loop(verdict: str, confidence: str, summary: Optional[dict] = None) -> str:
    """Tool called by the Judge to accept the trial and return a verdict.

    Returns a JSON string so the caller can parse and validate fields.
    """

    payload: dict[str, Any] = {
        "verdict": (verdict or "").strip(),
        "confidence": (confidence or "").strip().lower(),
    }
    if summary is not None:
        payload["summary"] = summary
    return json.dumps(payload, ensure_ascii=False)


@dataclass(slots=True)
class JudgeDecision:
    """Represents the Judge's decision after deliberation."""

    accepted: bool
    verdict: str = ""
    confidence: str = ""
    summary: Dict[str, Any] | None = None
    feedback: str = ""
    suggested_queries_admirer: list[str] = field(default_factory=list)
    suggested_queries_critic: list[str] = field(default_factory=list)


class JudgeAgent:
    """The Judge agent that evaluates evidence and controls trial flow."""

    def __init__(
        self,
        *,
        max_rounds: int = 3,
        model: object = "gemini-2.5-flash",
        app_name: str = "historical-court",
        generate_content_config: object | None = None,
    ):
        if not isinstance(max_rounds, int) or max_rounds < 1:
            raise ValueError("max_rounds must be an integer >= 1")

        self.max_rounds = max_rounds
        self.model = model
        self.app_name = app_name

        self.agent = Agent(
            name="judge",
            model=self.model,
            instruction=JUDGE_SYSTEM_PROMPT,
            description="Impartial arbiter that evaluates evidence and decides verdict.",
            tools=[exit_loop],
            generate_content_config=generate_content_config,
        )
        self.runner = InMemoryRunner(agent=self.agent, app_name=self.app_name)
        self.user_id = "judge_user"
        # NOTE: Using a fixed session_id causes the InMemoryRunner to accumulate conversation
        # history across rounds, which can bloat context and trigger API "internal" failures.
        # Default to stateless-by-round behavior; can be overridden via ADK_STATEFUL_SESSIONS=1.
        self.session_id = "judge_session"

    @staticmethod
    def _format_evidence(
        evidence: list,
        *,
        max_chars: int | None = None,
        max_item_chars: int | None = None,
    ) -> str:
        def _truncate_sentence(text: str, limit: int) -> str:
            if len(text) <= limit:
                return text
            truncated = text[:limit]
            last_period = truncated.rfind(".")
            last_exclaim = truncated.rfind("!")
            last_question = truncated.rfind("?")
            cutoff = max(last_period, last_exclaim, last_question)
            if cutoff > limit * 0.7:
                return truncated[: cutoff + 1].rstrip() + " ...(truncated)"
            return text[: limit - 15].rstrip() + " ...(truncated)"

        max_chars = max_chars or int(os.environ.get("JUDGE_EVIDENCE_MAX_CHARS", "2400"))
        max_item_chars = max_item_chars or int(os.environ.get("JUDGE_EVIDENCE_MAX_ITEM_CHARS", "900"))

        items: list[str] = []
        for i, e in enumerate(evidence or [], start=1):
            if e is None:
                continue
            s = str(e).strip()
            if not s:
                continue
            # Normalize whitespace to reduce prompt bloat
            s = " ".join(s.split())
            s = _truncate_sentence(s, max_item_chars)
            items.append(f"[{i}] {s}")

        out = "\n\n".join(items).strip() or "(none)"
        if len(out) <= max_chars:
            return out

        return _truncate_sentence(out, max_chars)

    def _build_deliberation_prompt(
        self,
        topic: str,
        positive_evidence: list,
        negative_evidence: list,
        round_number: int,
    ) -> str:
        t = (topic or "").strip() or "(unknown topic)"

        pos_block = self._format_evidence(positive_evidence)
        neg_block = self._format_evidence(negative_evidence)

        rn = int(round_number) if isinstance(round_number, int) else 0
        
        is_final_round = rn >= self.max_rounds
        
        prompt = (
            f"TOPIC: {t}\n\n"
            "EVIDENCE FROM THE ADMIRER (POSITIVE):\n"
            f"{pos_block}\n\n"
            "EVIDENCE FROM THE CRITIC (NEGATIVE):\n"
            f"{neg_block}\n\n"
            f"CURRENT ROUND: {rn} of {self.max_rounds}\n\n"
        )
        
        if is_final_round:
            prompt += (
                "🚨 FINAL ROUND ALERT 🚨\n"
                "This is the FINAL round. You are PROHIBITED from requesting more evidence.\n"
                "You MUST call the `exit_loop` tool now.\n"
                "Render your verdict based on whatever evidence you have, even if imperfect.\n"
                "Do NOT provide feedback. Do NOT ask for queries. CALL `exit_loop` IMMEDIATELY.\n"
            )
        else:
            prompt += (
                "Deliberate carefully.\n"
                "- If evidence is sufficient and balanced, call exit_loop.\n"
                "- If evidence is insufficient, provide specific feedback for the next round.\n"
            )

        return prompt

    @staticmethod
    def _is_resource_exhausted(err: Exception) -> bool:
        """Detect Google ADK/GenAI rate limit (429) errors robustly.
        
        Walks exception chain to catch:
        - google.adk.models.google_llm._ResourceExhaustedError (ADK wrapper)
        - google.genai.errors.ClientError with status 429
        - Any exception containing "RESOURCE_EXHAUSTED" or "429"
        """
        # Walk exception chain
        current = err
        while current is not None:
            # Check class name for Google ADK specific errors
            cls_name = current.__class__.__name__
            module_name = current.__class__.__module__
            
            # Check for Google ADK ResourceExhaustedError
            if cls_name == "_ResourceExhaustedError" and "google.adk.models.google_llm" in module_name:
                return True
            
            # Check for Google GenAI ClientError with status 429
            if cls_name == "ClientError" and "google.genai.errors" in module_name:
                # Check if it's a 429 error
                err_str = str(current).upper()
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    return True
            
            # Check error message for common patterns
            msg = str(current).upper()
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                return True
            
            # Move to __cause__ or __context__
            if hasattr(current, "__cause__") and current.__cause__:
                current = current.__cause__
            elif hasattr(current, "__context__") and current.__context__:
                current = current.__context__
            else:
                break
        
        return False

    def _session_id_for_round(self, round_number: int) -> str:
        """Return a session_id for this deliberation call.

        By default this is *stateless* (unique per call) to avoid runaway context growth.
        Set ADK_STATEFUL_SESSIONS=1 to keep a stable session across rounds.
        """
        stateful = (os.environ.get("ADK_STATEFUL_SESSIONS", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
        if stateful:
            return self.session_id
        rn = int(round_number) if isinstance(round_number, int) else 0
        return f"{self.session_id}_r{rn}_{uuid.uuid4().hex[:8]}"

    async def deliberate(
        self,
        topic: str,
        positive_evidence: list,
        negative_evidence: list,
        round_number: int,
    ) -> JudgeDecision:
        prompt = self._build_deliberation_prompt(topic, positive_evidence, negative_evidence, round_number)

        max_attempts = int(os.environ.get("ADK_JUDGE_RETRIES", "3") or "3")
        base_delay = float(os.environ.get("ADK_JUDGE_RETRY_BASE_SECONDS", "1.5") or "1.5")

        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                self.agent.instruction = JUDGE_SYSTEM_PROMPT.format(round_count=round_number, max_rounds=self.max_rounds)
                session_id = self._session_id_for_round(round_number)
                logger.debug(
                    "Judge deliberation start",
                    extra={
                        "topic": (topic or "").strip(),
                        "round_number": round_number,
                        "pos_items": len(positive_evidence or []),
                        "neg_items": len(negative_evidence or []),
                        "prompt_chars": len(prompt),
                        "session_id": session_id,
                    },
                )
                events = await self.runner.run_debug(
                    prompt,
                    user_id=self.user_id,
                    session_id=session_id,
                    quiet=True,
                )
                last_error = None
                break

            except Exception as e:
                last_error = e
                if self._is_resource_exhausted(e) and attempt < max_attempts - 1:
                    # Improved backoff for rate limiting errors
                    # Base delay: longer for 429 errors (3 seconds) vs default (1.5 seconds)
                    rate_limit_base = 3.0  # seconds for 429 errors
                    # Exponential backoff: rate_limit_base * 2^attempt
                    exp_delay = rate_limit_base * (2 ** attempt)
                    # Add jitter: random factor between 0.5 and 1.5
                    jitter = 0.5 + random.random()  # 0.5 to 1.5
                    delay = exp_delay * jitter
                    # Cap at 30 seconds
                    delay = min(delay, 30.0)
                    logger.warning(
                        "Judge rate limit (429) detected, retrying after backoff",
                        extra={
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "delay_seconds": round(delay, 2),
                            "error_type": type(e).__name__,
                        },
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        if last_error is not None:
            logger.error(
                "Judge deliberation failed",
                exc_info=last_error,
                extra={"topic": (topic or "").strip(), "error": str(last_error), "round_number": round_number},
            )

            expose = (os.environ.get("EXPOSE_JUDGE_INTERNAL_ERRORS", "0") or "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
            }
            extra_msg = f" ({type(last_error).__name__}: {last_error})" if expose else ""

            # Determine if this is a rate limit error
            is_rate_limit = self._is_resource_exhausted(last_error)
            
            if is_rate_limit:
                feedback_msg = (
                    "The Judge could not deliberate because the AI model quota/rate limit was exceeded." + extra_msg + " "
                    "This is a temporary service limitation; please try again in a few moments."
                )
            else:
                feedback_msg = (
                    "The Judge could not deliberate due to an internal error" + extra_msg + ". "
                    "Please repeat the round with shorter, more specific evidence blocks."
                )
            
            return JudgeDecision(
                accepted=False,
                feedback=feedback_msg,
            )

        tool_result = extract_tool_result(events, "exit_loop")
        if tool_result is None:
            logger.debug(
                "Judge produced no exit_loop tool part (no function_call/response found)",
                extra={"topic": (topic or "").strip(), "round_number": round_number},
            )
            # FORCE VERDICT ON FINAL ROUND
            # If the model refused to call exit_loop even when told to, we force it here.
            # This handles cases where the model writes a verdict in text but forgets the tool call,
            # or just stubbornly refuses.
            if round_number >= self.max_rounds:
                logger.warning(
                    "Judge failed to call exit_loop in final round. Forcing verdict from text output.",
                    extra={"topic": topic, "round_number": round_number}
                )
                text_output = (extract_text(events) or "").strip()
                return JudgeDecision(
                    accepted=True,
                    verdict=text_output if text_output else "The Judge failed to render a formal verdict but the trial has concluded.",
                    confidence="low (forced)",
                    summary={"reason": "Max rounds reached, forced conclusion"},
                )

            feedback = (extract_text(events) or "").strip()
            if not feedback:
                feedback = "Insufficient evidence formatting/quality. Provide 2-3 concrete, verifiable facts per side."

            # Parse suggested queries from feedback
            import re
            
            admirer_queries = []
            critic_queries = []
            
            # Simple parsing of bullet points under headers
            lines = feedback.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if "SUGGESTED QUERIES FOR ADMIRER" in line.upper():
                    current_section = "admirer"
                    continue
                elif "SUGGESTED QUERIES FOR CRITIC" in line.upper():
                    current_section = "critic"
                    continue
                elif line.upper().startswith("SUGGESTED QUERIES"):
                    current_section = None # reset if ambiguous header
                
                if current_section and (line.startswith('-') or line.startswith('*') or line[0:1].isdigit()):
                    # Extract query from quotes if present, otherwise whole line
                    match = re.search(r'["\']([^"\']+)["\']', line)
                    query = match.group(1) if match else re.sub(r'^[-*0-9.)\s]+', '', line).strip()
                    
                    if query:
                        if current_section == "admirer":
                            admirer_queries.append(query)
                        elif current_section == "critic":
                            critic_queries.append(query)

            logger.info(
                "Judge rejected (no exit_loop tool call)",
                extra={
                    "topic": (topic or "").strip(),
                    "round_number": round_number,
                    "admirer_suggestions": len(admirer_queries),
                    "critic_suggestions": len(critic_queries)
                },
            )
            return JudgeDecision(
                accepted=False,
                feedback=feedback,
                suggested_queries_admirer=admirer_queries,
                suggested_queries_critic=critic_queries
            )

        verdict = (tool_result.get("verdict") if isinstance(tool_result, dict) else "") or ""
        confidence = (tool_result.get("confidence") if isinstance(tool_result, dict) else "") or ""
        summary = (tool_result.get("summary") if isinstance(tool_result, dict) else None)

        verdict = str(verdict).strip()
        confidence = str(confidence).strip()

        # Allow "FORCED" values or standard levels
        if confidence and confidence.lower() not in {"low", "medium", "high"} and not confidence.startswith("FORCED"):
            confidence = ""

        if not verdict or not confidence:
            raw = ""
            try:
                raw = json.dumps(tool_result, ensure_ascii=False)[:800]
            except Exception:
                raw = str(tool_result)[:800]

            logger.warning(
                "Judge produced malformed exit_loop call; treating as rejection",
                extra={"topic": (topic or "").strip(), "round_number": round_number, "tool_args": raw},
            )

            feedback = (
                "Your exit_loop tool call was malformed or incomplete. "
                "If accepting, you must call exit_loop with verdict (string) and confidence (low|medium|high). "
                "Otherwise, provide feedback without calling tools."
            )
            return JudgeDecision(accepted=False, feedback=feedback)

        summary_out: Dict[str, Any] | None = None
        if isinstance(summary, dict):
            summary_out = summary

        logger.info(
            "Judge accepted via exit_loop",
            extra={"topic": (topic or "").strip(), "round_number": round_number, "confidence": confidence},
        )

        return JudgeDecision(
            accepted=True,
            verdict=verdict,
            confidence=confidence,
            summary=summary_out,
        )
