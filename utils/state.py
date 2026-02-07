from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Dict, List


class TrialStatus(Enum):
    """Enum representing the current status of the trial."""

    IDLE = "idle"
    INITIALIZED = "initialized"
    RESEARCHING = "researching"
    DELIBERATING = "deliberating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FORCED_TERMINATION = "forced_termination"
    GENERATING_VERDICT = "generating_verdict"
    COMPLETED = "completed"


@dataclass
class CourtState:
    """Central state management for The Historical Court trial process.

    This class maintains all shared state between agents including:
    - The topic being investigated
    - Evidence collected by Admirer (pos_data) and Critic (neg_data)
    - Current round number and maximum rounds
    - Judge's feedback for subsequent rounds
    - Trial status tracking
    """

    topic: str
    pos_data: List[str] = field(default_factory=list)
    neg_data: List[str] = field(default_factory=list)
    used_queries_admirer: List[str] = field(default_factory=list)
    used_queries_critic: List[str] = field(default_factory=list)
    evidence_hashes: Set[str] = field(default_factory=set)
    seen_titles_admirer: Set[str] = field(default_factory=set)
    seen_titles_critic: Set[str] = field(default_factory=set)
    rounds: int = 0
    max_rounds: int = 3
    feedback: str = ""
    suggested_queries_admirer: List[str] = field(default_factory=list)
    suggested_queries_critic: List[str] = field(default_factory=list)
    status: TrialStatus = TrialStatus.IDLE
    created_at: datetime = field(default_factory=datetime.now)

    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate initial state values."""
        if not isinstance(self.topic, str) or not self.topic.strip():
            raise ValueError("topic must be a non-empty string")

        if not isinstance(self.max_rounds, int) or self.max_rounds < 1:
            raise ValueError("max_rounds must be an integer >= 1")

        if not isinstance(self.rounds, int) or self.rounds < 0:
            raise ValueError("rounds must be an integer >= 0")

        if self.rounds > self.max_rounds:
            raise ValueError("rounds cannot be greater than max_rounds")

        if not isinstance(self.pos_data, list) or not all(isinstance(x, str) for x in self.pos_data):
            raise ValueError("pos_data must be a list[str]")

        if not isinstance(self.neg_data, list) or not all(isinstance(x, str) for x in self.neg_data):
            raise ValueError("neg_data must be a list[str]")

        if not isinstance(self.used_queries_admirer, list) or not all(isinstance(x, str) for x in self.used_queries_admirer):
            raise ValueError("used_queries_admirer must be a list[str]")

        if not isinstance(self.used_queries_critic, list) or not all(isinstance(x, str) for x in self.used_queries_critic):
            raise ValueError("used_queries_critic must be a list[str]")

        if not isinstance(self.evidence_hashes, set) or not all(isinstance(x, str) for x in self.evidence_hashes):
            raise ValueError("evidence_hashes must be a set[str]")

        if not isinstance(self.seen_titles_admirer, set) or not all(isinstance(x, str) for x in self.seen_titles_admirer):
            raise ValueError("seen_titles_admirer must be a set[str]")

        if not isinstance(self.seen_titles_critic, set) or not all(isinstance(x, str) for x in self.seen_titles_critic):
            raise ValueError("seen_titles_critic must be a set[str]")

        if not isinstance(self.feedback, str):
            raise ValueError("feedback must be a string")

        if not isinstance(self.suggested_queries_admirer, list) or not all(isinstance(x, str) for x in self.suggested_queries_admirer):
            raise ValueError("suggested_queries_admirer must be a list[str]")

        if not isinstance(self.suggested_queries_critic, list) or not all(isinstance(x, str) for x in self.suggested_queries_critic):
            raise ValueError("suggested_queries_critic must be a list[str]")

        if not isinstance(self.status, TrialStatus):
            raise ValueError("status must be a TrialStatus")

    def add_positive_evidence(self, evidence: str, title: str = "") -> None:
        """Add a single piece of evidence from the Admirer.

        Args:
            evidence: A non-empty evidence string.
            title: Title of the source (optional)

        Raises:
            ValueError: If evidence is empty.
            RuntimeError: If the trial is in a terminal/non-mutable status.
        """
        evidence = (evidence or "").strip()
        if not evidence:
            raise ValueError("evidence must be a non-empty string")

        with self._lock:
            self._ensure_mutable()
            self.pos_data.append(evidence)
            if title:
                self.seen_titles_admirer.add(title)

    def add_negative_evidence(self, evidence: str, title: str = "") -> None:
        """Add a single piece of evidence from the Critic.

        Args:
            evidence: A non-empty evidence string.
            title: Title of the source (optional)

        Raises:
            ValueError: If evidence is empty.
            RuntimeError: If the trial is in a terminal/non-mutable status.
        """
        evidence = (evidence or "").strip()
        if not evidence:
            raise ValueError("evidence must be a non-empty string")

        with self._lock:
            self._ensure_mutable()
            self.neg_data.append(evidence)
            if title:
                self.seen_titles_critic.add(title)

    def increment_round(self) -> bool:
        """Increment the current round counter.

        Returns:
            True if the round was incremented, False if max_rounds has already been reached.

        Raises:
            RuntimeError: If the trial is in a terminal/non-mutable status.
        """
        with self._lock:
            self._ensure_mutable()

            if self.rounds >= self.max_rounds:
                return False

            self.rounds += 1
            return True

    def set_feedback(self, feedback: str, suggested_queries_admirer: List[str] = None, suggested_queries_critic: List[str] = None) -> None:
        """Set judge feedback used to guide subsequent research rounds.

        Args:
            feedback: Feedback text (may be empty).
            suggested_queries_admirer: Specific queries for admirer to try
            suggested_queries_critic: Specific queries for critic to try

        Raises:
            RuntimeError: If the trial is in a terminal/non-mutable status.
        """
        with self._lock:
            self._ensure_mutable()
            self.feedback = (feedback or "").strip()
            if suggested_queries_admirer is not None:
                self.suggested_queries_admirer = list(suggested_queries_admirer)
            if suggested_queries_critic is not None:
                self.suggested_queries_critic = list(suggested_queries_critic)

    def update_status(self, status: TrialStatus) -> None:
        """Update the trial status while enforcing valid state transitions.

        Args:
            status: The next status to transition to.

        Raises:
            ValueError: If status is not a TrialStatus.
            RuntimeError: If the transition is invalid.
        """
        if not isinstance(status, TrialStatus):
            raise ValueError("status must be a TrialStatus")

        with self._lock:
            if status == self.status:
                return

            if status not in self._allowed_next_statuses(self.status):
                raise RuntimeError(f"invalid status transition: {self.status.value} -> {status.value}")

            self.status = status

    def is_complete(self) -> bool:
        """Return True if the trial has reached a completed terminal state."""
        with self._lock:
            return self.status == TrialStatus.COMPLETED

    def can_continue(self) -> bool:
        """Return True if the trial loop can continue safely.

        The trial can continue if it is not completed and the round limit has not been exceeded.
        """
        with self._lock:
            if self.status == TrialStatus.COMPLETED:
                return False

            if self.rounds >= self.max_rounds and self.status in {TrialStatus.REJECTED, TrialStatus.RESEARCHING, TrialStatus.DELIBERATING}:
                return False

            return True

    def get_evidence_summary(self) -> Dict[str, object]:
        """Get a structured summary of evidence and key state fields.

        Returns:
            A dictionary containing counts and recent evidence for logging/monitoring.
        """
        with self._lock:
            return {
                "topic": self.topic,
                "status": self.status.value,
                "rounds": self.rounds,
                "max_rounds": self.max_rounds,
                "feedback": self.feedback,
                "pos_count": len(self.pos_data),
                "neg_count": len(self.neg_data),
                "latest_positive": self.pos_data[-1] if self.pos_data else None,
                "latest_negative": self.neg_data[-1] if self.neg_data else None,
                "created_at": self.created_at.isoformat(),
            }

    def to_dict(self) -> Dict[str, object]:
        """Serialize the state to a JSON-friendly dictionary."""
        with self._lock:
            return {
                "topic": self.topic,
                "pos_data": list(self.pos_data),
                "neg_data": list(self.neg_data),
                "used_queries_admirer": list(self.used_queries_admirer),
                "used_queries_critic": list(self.used_queries_critic),
                "rounds": self.rounds,
                "max_rounds": self.max_rounds,
                "feedback": self.feedback,
                "status": self.status.value,
                "created_at": self.created_at.isoformat(),
            }

    def __str__(self) -> str:
        """Return a compact string representation suitable for logs."""
        with self._lock:
            return (
                f"CourtState(topic={self.topic!r}, status={self.status.value!r}, "
                f"rounds={self.rounds}/{self.max_rounds}, pos={len(self.pos_data)}, neg={len(self.neg_data)})"
            )

    def _ensure_mutable(self) -> None:
        """Raise if the state should no longer be mutated."""
        if self.status in {TrialStatus.COMPLETED, TrialStatus.GENERATING_VERDICT}:
            raise RuntimeError(f"cannot mutate state when status={self.status.value}")

    @staticmethod
    def _allowed_next_statuses(current: TrialStatus) -> set[TrialStatus]:
        """Return the allowed next statuses given a current status."""
        transitions: dict[TrialStatus, set[TrialStatus]] = {
            TrialStatus.IDLE: {TrialStatus.INITIALIZED},
            TrialStatus.INITIALIZED: {TrialStatus.RESEARCHING},
            TrialStatus.RESEARCHING: {TrialStatus.DELIBERATING, TrialStatus.RESEARCHING},
            TrialStatus.DELIBERATING: {TrialStatus.ACCEPTED, TrialStatus.REJECTED},
            TrialStatus.REJECTED: {TrialStatus.RESEARCHING, TrialStatus.FORCED_TERMINATION},
            TrialStatus.ACCEPTED: {TrialStatus.GENERATING_VERDICT},
            TrialStatus.FORCED_TERMINATION: {TrialStatus.GENERATING_VERDICT},
            TrialStatus.GENERATING_VERDICT: {TrialStatus.COMPLETED},
            TrialStatus.COMPLETED: set(),
        }
        return transitions.get(current, set())
