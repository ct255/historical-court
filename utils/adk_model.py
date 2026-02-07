from __future__ import annotations

import os
from typing import Any, Optional

from google.adk.models.google_llm import Gemini


def build_gemini_model(
    model_name: str,
    *,
    use_vertexai: Optional[bool] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
) -> Any:
    """Build an ADK Gemini model configuration.

    If Vertex AI is requested (or implied by credentials), returns a Gemini model
    configured for Vertex AI. Otherwise returns the model name string for Gemini API.
    """

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    project = (project or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT") or "").strip()
    location = (location or os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCLOUD_LOCATION") or "").strip()

    if use_vertexai is None:
        use_vertexai = bool(credentials_path) and not bool(api_key)

    if use_vertexai:
        if not project or not location:
            raise ValueError(
                "Vertex AI requires project and location. "
                "Set --project/--location or GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION."
            )
        return Gemini(
            model=model_name,
            vertexai=True,
            project=project,
            location=location,
        )

    if not api_key and credentials_path:
        raise ValueError(
            "Credentials file provided but Vertex AI is not configured. "
            "Set --project/--location or GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION, "
            "or set GOOGLE_API_KEY/GEMINI_API_KEY."
        )

    return model_name
