import os
from typing import Protocol, runtime_checkable

from google.adk import Agent
from google.adk.runners import InMemoryRunner

@runtime_checkable
class BaseProvider(Protocol):
    """Protocol defining the interface for LLM providers."""

    def create_agent(
        self,
        *,
        name: str,
        instruction: str,
        description: str | None = None,
        tools: list | None = None,
    ) -> Agent:
        """Create an ADK Agent instance."""
        ...

    def create_runner(self, agent: Agent) -> InMemoryRunner:
        """Create an ADK runner for a given agent."""
        ...


class AdkProvider:
    """Google ADK implementation of the BaseProvider."""

    def __init__(self, *, api_key: str | None = None, model_name: str = "gemini-2.5-flash", app_name: str = "historical-court"):
        self.model_name = model_name
        self.app_name = app_name

        if api_key:
            os.environ.setdefault("GOOGLE_API_KEY", api_key)

    def create_agent(
        self,
        *,
        name: str,
        instruction: str,
        description: str | None = None,
        tools: list | None = None,
    ) -> Agent:
        return Agent(
            name=name,
            model=self.model_name,
            instruction=instruction,
            description=description or "",
            tools=tools or [],
        )

    def create_runner(self, agent: Agent) -> InMemoryRunner:
        return InMemoryRunner(agent=agent, app_name=self.app_name)
