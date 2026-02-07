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
from dataclasses import dataclass
from typing import Any, Dict, Optional

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
1. BALANCE: Both sides should have substantial evidence (at least 2-3 meaningful facts each)
2. RELEVANCE: Evidence should be directly related to the topic
3. QUALITY: Evidence should be specific, verifiable, and substantive
4. COMPLETENESS: The overall picture should be comprehensive

Decision Options:

REJECT (Continue Trial):
- If one side has significantly less evidence than the other
- If evidence is too vague or generic
- If important aspects haven't been explored
- Provide specific feedback for the weaker side to improve

ACCEPT (End Trial):
- If both sides have presented balanced, substantial evidence
- If the topic has been thoroughly examined
- If additional rounds would not significantly improve the verdict
- Call the exit_loop function with a balanced verdict summary

When accepting, generate a verdict that:
- Summarizes key points from both perspectives
- Presents a balanced, nuanced view
- Acknowledges complexity and controversy where present
- Is written in a formal, judicial tone

Round Awareness:
Current round: {round_count} of {max_rounds}
- If this is the final round, you MUST accept and render a verdict with available evidence.
- Earlier rounds allow more flexibility to request additional evidence.

Tool Instructions:
- To ACCEPT you MUST call exit_loop with required fields.
- To REJECT you MUST provide actionable feedback in plain text.
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
        self.session_id = "judge_session"

    @staticmethod
    def _format_evidence(evidence: list, *, max_chars: int = 6000) -> str:
        items: list[str] = []
        for i, e in enumerate(evidence or [], start=1):
            if e is None:
                continue
            s = str(e).strip()
            if not s:
                continue
            items.append(f"[{i}] {s}")

        out = "\n\n".join(items).strip() or "(none)"
        if len(out) <= max_chars:
            return out
        return out[: max_chars - 20].rstrip() + "\n\n...(truncated)"

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
        prompt = (
            f"TOPIC: {t}\n\n"
            "EVIDENCE FROM THE ADMIRER (POSITIVE):\n"
            f"{pos_block}\n\n"
            "EVIDENCE FROM THE CRITIC (NEGATIVE):\n"
            f"{neg_block}\n\n"
            f"CURRENT ROUND: {rn} of {self.max_rounds}\n\n"
            "Deliberate carefully.\n"
            "- If evidence is sufficient and balanced, call exit_loop.\n"
            "- If evidence is insufficient, provide specific feedback for the next round.\n"
        )
        return prompt

    @staticmethod
    def _is_resource_exhausted(err: Exception) -> bool:
        msg = str(err).upper()
        return "RESOURCE_EXHAUSTED" in msg or "429" in msg

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
                logger.debug(
                    "Judge deliberation start",
                    extra={
                        "topic": (topic or "").strip(),
                        "round_number": round_number,
                        "pos_items": len(positive_evidence or []),
                        "neg_items": len(negative_evidence or []),
                    },
                )
                events = await self.runner.run_debug(
                    prompt,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    quiet=True,
                )
                last_error = None
                break

            except Exception as e:
                last_error = e
                if self._is_resource_exhausted(e) and attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                break

        if last_error is not None:
            logger.info(
                "Judge deliberation failed",
                extra={"topic": (topic or "").strip(), "error": str(last_error)},
            )
            return JudgeDecision(
                accepted=False,
                feedback=(
                    "The Judge could not deliberate due to an internal error. "
                    "Please repeat the round with shorter, more specific evidence blocks."
                ),
            )

        tool_result = extract_tool_result(events, "exit_loop")
        if tool_result is None:
            feedback = (extract_text(events) or "").strip()
            if not feedback:
                feedback = "Insufficient evidence formatting/quality. Provide 2-3 concrete, verifiable facts per side."

            logger.info(
                "Judge rejected (no exit_loop tool call)",
                extra={"topic": (topic or "").strip(), "round_number": round_number},
            )
            return JudgeDecision(accepted=False, feedback=feedback)

        verdict = (tool_result.get("verdict") if isinstance(tool_result, dict) else "") or ""
        confidence = (tool_result.get("confidence") if isinstance(tool_result, dict) else "") or ""
        summary = (tool_result.get("summary") if isinstance(tool_result, dict) else None)

        verdict = str(verdict).strip()
        confidence = str(confidence).strip().lower()

        if confidence and confidence not in {"low", "medium", "high"}:
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
