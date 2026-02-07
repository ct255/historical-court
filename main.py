"""
The Historical Court - Main Orchestration Loop

This is the entry point that coordinates the trial workflow:
1. Initialize agents and state
2. Run Admirer and Critic in parallel (asyncio.gather)
3. Have the Judge evaluate evidence
4. Loop or terminate based on Judge's decision
5. Save the final verdict to file
"""

import asyncio
import os
import re
import sys
import logging
import hashlib
from datetime import datetime
from typing import Optional

from google.genai import types

from utils.state import CourtState, TrialStatus
from utils.display import TrialDisplay
from agents.admirer import AdmirerAgent
from agents.critic import CriticAgent
from agents.judge import JudgeAgent, JudgeDecision
from utils.adk_model import build_gemini_model
from utils.config import load_environment, get_model_name, get_env


# Configure logging
def _resolve_log_level(value: str | None) -> int:
    if not value:
        return logging.WARNING
    name = value.strip().upper()
    return getattr(logging, name, logging.WARNING)


logging.basicConfig(
    level=_resolve_log_level(get_env("LOG_LEVEL")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Quiet noisy third-party loggers by default
_noisy_loggers: dict[str, int] = {
    "google": logging.WARNING,
    "google_adk": logging.WARNING,
    "google_genai": logging.WARNING,
    "google_genai.types": logging.ERROR,
    "grpc": logging.WARNING,
    "urllib3": logging.WARNING,
    "agents.judge": logging.ERROR,
}
for noisy_logger, level in _noisy_loggers.items():
    logging.getLogger(noisy_logger).setLevel(level)

logger = logging.getLogger(__name__)

# Load environment variables from .env if present
load_environment()
del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
# force add key.json to env
if os.path.isfile("key.json"):
    print("Using key.json for GOOGLE_APPLICATION_CREDENTIALS")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

# Configuration
MAX_ROUNDS = 3
OUTPUT_DIR = "output"
API_KEY_ENV = "GOOGLE_API_KEY"  # or "GEMINI_API_KEY"
MODEL_NAME = get_model_name()
SHOW_STEPS = True
ENABLE_PARALLEL = False


async def run_parallel_research(
    admirer: AdmirerAgent,
    critic: CriticAgent,
    topic: str,
    feedback: str = "",
    used_queries_admirer: list[str] = None,
    used_queries_critic: list[str] = None,
    suggested_queries_admirer: list[str] = None,
    suggested_queries_critic: list[str] = None,
) -> tuple[str, str, str, str]:
    """
    Run both agents in parallel using asyncio.gather.

    This is the key demonstration of parallelism.

    Args:
        admirer: The Admirer agent instance
        critic: The Critic agent instance
        topic: The subject being researched
        feedback: Optional feedback from the Judge
        used_queries_admirer: List of previously used queries by Admirer
        used_queries_critic: List of previously used queries by Critic
        suggested_queries_admirer: Optional list of specific queries suggested by Judge
        suggested_queries_critic: Optional list of specific queries suggested by Judge

    Returns:
        Tuple of (admirer_query, admirer_findings, critic_query, critic_findings)
    """
    if ENABLE_PARALLEL:
        # Use asyncio.gather to run both concurrently
        admirer_task = admirer.research_with_query(topic, feedback, used_queries_admirer, suggested_queries_admirer)
        critic_task = critic.research_with_query(topic, feedback, used_queries_critic, suggested_queries_critic)

        admirer_result, critic_result = await asyncio.gather(
            admirer_task,
            critic_task,
            return_exceptions=True,  # Don't fail if one agent fails
        )
    else:
        admirer_result = await admirer.research_with_query(
            topic, feedback, used_queries_admirer, suggested_queries_admirer
        )
        critic_result = await critic.research_with_query(
            topic, feedback, used_queries_critic, suggested_queries_critic
        )

    # Handle exceptions gracefully
    if isinstance(admirer_result, Exception):
        logger.info(f"Admirer failed: {admirer_result}")
        admirer_result = ("", "Error gathering positive evidence")

    if isinstance(critic_result, Exception):
        logger.info(f"Critic failed: {critic_result}")
        critic_result = ("", "Error gathering critical evidence")

    admirer_query, admirer_findings = admirer_result
    critic_query, critic_findings = critic_result
    return admirer_query, admirer_findings, critic_query, critic_findings


def _count_pages(text: str) -> int:
    return len(re.findall(r"^Page:\s+", text or "", flags=re.MULTILINE))


def _evidence_hash(evidence: str) -> str:
    return hashlib.md5(evidence.encode()).hexdigest()


def save_verdict(
    topic: str, verdict: str, state: CourtState, decision: Optional[JudgeDecision]
) -> str:
    """
    Save the final verdict to a text file.

    Args:
        topic: The subject of the trial
        verdict: The Judge's final verdict
        state: The final court state
        decision: The Judge's decision object

    Returns:
        Path to the saved file
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = now.strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() else "_" for c in topic.lower())
    filename = f"verdict_{safe_topic}_{file_timestamp}.txt"
    path = os.path.join(OUTPUT_DIR, filename)

    pos_summary = (
        "\n\n".join(state.pos_data)
        if state.pos_data
        else "(No positive evidence gathered)"
    )
    neg_summary = (
        "\n\n".join(state.neg_data)
        if state.neg_data
        else "(No negative evidence gathered)"
    )

    confidence_str = ""
    summary_str = ""

    if decision:
        if hasattr(decision, "confidence") and decision.confidence:
            confidence_str = f"Confidence Score: {decision.confidence}\n"

        if hasattr(decision, "summary") and decision.summary:
            import json

            summary_str = f"Key Factors:\n{json.dumps(decision.summary, indent=2)}\n"

    content = f"""================================================================
THE HISTORICAL COURT - VERDICT
================================================================
Topic: {topic}
Date: {timestamp}
Rounds: {state.rounds}
{confidence_str}================================================================

THE ADMIRER'S CASE:
{pos_summary}

THE CRITIC'S CASE:
{neg_summary}

FINAL VERDICT:
{verdict}

{summary_str}================================================================
"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Verdict saved to {path}")
    return path


async def run_trial(topic: str, *, model: object) -> str:
    """
    Execute the complete trial workflow.

    Args:
        topic: The historical figure/event to try
        api_key: Google API key for Gemini

    Returns:
        The final verdict text
    """
    display = TrialDisplay(show_steps=SHOW_STEPS)

    # 1. Initialize
    display.show_header(topic, MODEL_NAME)

    state = CourtState(topic=topic, max_rounds=MAX_ROUNDS)
    state.update_status(TrialStatus.INITIALIZED)

    afc_max = os.environ.get("AFC_MAX_REMOTE_CALLS")
    generate_content_config = None
    if afc_max:
        try:
            max_calls = int(afc_max)
            generate_content_config = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=max_calls
                )
            )
        except ValueError:
            logger.warning(
                "Invalid AFC_MAX_REMOTE_CALLS; must be integer",
                extra={"value": afc_max},
            )

    admirer = AdmirerAgent(model=model, generate_content_config=generate_content_config)
    critic = CriticAgent(model=model, generate_content_config=generate_content_config)
    judge = JudgeAgent(
        model=model,
        max_rounds=MAX_ROUNDS,
        generate_content_config=generate_content_config,
    )

    # 2. The Trial Loop
    while state.can_continue():
        state.increment_round()
        state.update_status(TrialStatus.RESEARCHING)

        display.show_round_start(state.rounds, MAX_ROUNDS)

        if state.feedback:
            display.show_judge_deliberation(
                f"Feedback for next round: {state.feedback}"
            )

        logger.info(f"=== Round {state.rounds} ===")

        # 3. Parallel Research (THE KEY ASYNC PATTERN)
        with display.progress_spinner("Agents are investigating...") as status:
            display.show_agent_action(
                "Admirer", "Searching for positive evidence...", is_loading=True
            )
            display.show_agent_action(
                "Critic", "Searching for critical evidence...", is_loading=True
            )

            adm_query, pos_evidence, crit_query, neg_evidence = (
                await run_parallel_research(
                    admirer,
                    critic,
                    topic,
                    state.feedback,
                    state.used_queries_admirer,
                    state.used_queries_critic,
                    state.suggested_queries_admirer,
                    state.suggested_queries_critic,
                )
            )

        display.show_evidence("Admirer", adm_query or "(no query)", pos_evidence)
        display.show_evidence("Critic", crit_query or "(no query)", neg_evidence)

        # Extract titles from evidence if possible (assuming "Page: Title" format)
        import re
        adm_title_match = re.search(r"Page:\s*(.*?)\n", pos_evidence)
        crit_title_match = re.search(r"Page:\s*(.*?)\n", neg_evidence)
        
        adm_title = adm_title_match.group(1).strip() if adm_title_match else ""
        crit_title = crit_title_match.group(1).strip() if crit_title_match else ""

        # 4. Update State with Deduplication
        if adm_query:
            state.used_queries_admirer.append(adm_query)
        if crit_query:
            state.used_queries_critic.append(crit_query)

        pos_hash = _evidence_hash(pos_evidence)
        # Check if title seen (if found) OR hash seen
        if pos_hash not in state.evidence_hashes:
            if adm_title and adm_title in state.seen_titles_admirer:
                 logger.info(f"Skipping duplicate positive title: {adm_title}")
            else:
                state.add_positive_evidence(pos_evidence, title=adm_title)
                state.evidence_hashes.add(pos_hash)
        else:
            logger.info("Skipping duplicate positive evidence (hash match)")

        neg_hash = _evidence_hash(neg_evidence)
        if neg_hash not in state.evidence_hashes:
            if crit_title and crit_title in state.seen_titles_critic:
                 logger.info(f"Skipping duplicate negative title: {crit_title}")
            else:
                state.add_negative_evidence(neg_evidence, title=crit_title)
                state.evidence_hashes.add(neg_hash)
        else:
            logger.info("Skipping duplicate negative evidence (hash match)")

        # 5. Judge Deliberation
        state.update_status(TrialStatus.DELIBERATING)
        with display.progress_spinner("Judge is deliberating...") as status:
            display.show_agent_action(
                "Judge", "Reviewing evidence and forming verdict...", is_loading=True
            )
            decision = await judge.deliberate(
                topic=topic,
                positive_evidence=state.pos_data,
                negative_evidence=state.neg_data,
                round_number=state.rounds,
            )

        # 6. Check Decision
        if decision.accepted:
            display.show_agent_action("Judge", "Verdict reached!", is_loading=False)
            state.update_status(TrialStatus.ACCEPTED)
            logger.info("Trial ACCEPTED - Generating verdict")

            display.show_verdict(topic, decision.verdict, decision)
            save_verdict(topic, decision.verdict, state, decision)
            return decision.verdict
        else:
            display.show_agent_action(
                "Judge", "Verdict rejected. Requesting more evidence.", is_loading=False
            )
            state.update_status(TrialStatus.REJECTED)
            state.set_feedback(
                decision.feedback,
                decision.suggested_queries_admirer,
                decision.suggested_queries_critic
            )
            logger.info(f"Trial REJECTED - Feedback: {decision.feedback[:100]}...")

    # 7. Forced termination after MAX_ROUNDS
    state.update_status(TrialStatus.FORCED_TERMINATION)
    display.show_agent_action(
        "Judge", "Max rounds reached. Issuing forced verdict.", is_loading=False
    )
    logger.warning("Max rounds reached - Forcing verdict generation")

    # Generate a verdict from current evidence
    # Deduplicate evidence while preserving order
    unique_pos = list(dict.fromkeys(state.pos_data))
    unique_neg = list(dict.fromkeys(state.neg_data))
    
    pos_text = "\n\n".join(unique_pos) if unique_pos else "No specific positive evidence gathered."
    neg_text = "\n\n".join(unique_neg) if unique_neg else "No specific negative evidence gathered."

    forced_verdict = (
        f"FORCED VERDICT (Max Rounds Reached) for '{topic}'\n\n"
        f"=== POSITIVE EVIDENCE ===\n{pos_text}\n\n"
        f"=== CRITICAL EVIDENCE ===\n{neg_text}\n\n"
        f"=== CONCLUSION ===\n"
        f"The historical significance of {topic} is complex. "
        f"Due to the trial reaching the maximum number of rounds without a consensus verdict, "
        f"the court acknowledges both the achievements and controversies presented above."
    )

    # Create a dummy decision for display
    dummy_decision = JudgeDecision(
        accepted=True,
        verdict=forced_verdict,
        confidence="FORCED - Insufficient Evidence",
        summary={"reason": "Max rounds reached"},
    )

    display.show_verdict(topic, forced_verdict, dummy_decision)
    save_verdict(topic, forced_verdict, state, dummy_decision)
    return forced_verdict


def main():
    """
    CLI entry point for The Historical Court.

    Usage: python main.py "Napoleon Bonaparte"
    """
    import argparse

    parser = argparse.ArgumentParser(description="The Historical Court")
    parser.add_argument("topic", help="Historical figure or event to try")
    parser.add_argument(
        "-c",
        "--credentials",
        dest="credentials_path",
        help="Path to Google service account JSON key file",
    )
    parser.add_argument(
        "--project",
        dest="project",
        help="Google Cloud project ID (required for Vertex AI)",
    )
    parser.add_argument(
        "--location",
        dest="location",
        help="Google Cloud region (e.g., us-central1) (required for Vertex AI)",
    )
    parser.add_argument(
        "--vertexai",
        action="store_true",
        help="Force Vertex AI mode (requires project & location)",
    )
    args = parser.parse_args()

    topic = args.topic

    api_key = get_env("GOOGLE_API_KEY") or get_env("GEMINI_API_KEY")
    credentials_path = args.credentials_path or get_env(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    project = (
        args.project or get_env("GOOGLE_CLOUD_PROJECT") or get_env("GCLOUD_PROJECT")
    )
    location = (
        args.location or get_env("GOOGLE_CLOUD_LOCATION") or get_env("GCLOUD_LOCATION")
    )

    # Use a temporary console for startup errors
    from rich.console import Console
    console = Console(stderr=True)

    if credentials_path:
        if not os.path.isfile(credentials_path):
            console.print(f"[bold red]Error:[/bold red] credentials file not found: {credentials_path}")
            sys.exit(1)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    if not api_key and not credentials_path:
        console.print("[bold red]Error:[/bold red] No Google credentials found.")
        console.print(
            "Set GOOGLE_API_KEY/GEMINI_API_KEY, or use --credentials /path/to/key.json,"
        )
        console.print("or set GOOGLE_APPLICATION_CREDENTIALS to the JSON key file path.")
        sys.exit(1)

    try:
        model = build_gemini_model(
            MODEL_NAME,
            use_vertexai=args.vertexai or bool(credentials_path),
            project=project,
            location=location,
        )
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    # Run the trial (TrialDisplay will handle output)
    asyncio.run(run_trial(topic, model=model))


if __name__ == "__main__":
    main()
