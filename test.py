import asyncio
import os
import sys

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from utils.adk_model import build_gemini_model
from utils.config import load_environment, get_model_name, get_env

load_environment()

MODEL_NAME = get_model_name()


def _require_google_credentials() -> None:
    api_key = get_env("GOOGLE_API_KEY") or get_env("GEMINI_API_KEY")
    credentials_path = get_env("GOOGLE_APPLICATION_CREDENTIALS")
    if not api_key and not credentials_path:
        raise ValueError(
            "No credentials found. Set GOOGLE_API_KEY/GEMINI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS."
        )


async def _run_once(model: object) -> None:
    agent = Agent(
        name="key_test",
        model=model,
        instruction="You are a helpful assistant. Reply with a short greeting.",
    )
    runner = InMemoryRunner(agent=agent, app_name="historical-court-key-test")

    events = await runner.run_debug("Hello", quiet=True)
    for event in events:
        content = getattr(event, "content", None)
        if not content or not getattr(content, "parts", None):
            continue
        for part in content.parts:
            text = getattr(part, "text", None)
            if text:
                print(text)
                return

    print("No text response returned.")


def main() -> None:
    # Use API key if present; otherwise use Vertex AI with credentials + project/location.
    _require_google_credentials()
    api_key = get_env("GOOGLE_API_KEY") or get_env("GEMINI_API_KEY")
    credentials_path = get_env("GOOGLE_APPLICATION_CREDENTIALS")

    project = get_env("GOOGLE_CLOUD_PROJECT") or get_env("GCLOUD_PROJECT")
    location = get_env("GOOGLE_CLOUD_LOCATION") or get_env("GCLOUD_LOCATION")

    model = build_gemini_model(
        MODEL_NAME,
        use_vertexai=bool(credentials_path) and not bool(api_key),
        project=project,
        location=location,
    )

    asyncio.run(_run_once(model))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
