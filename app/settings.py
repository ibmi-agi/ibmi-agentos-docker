"""
App Settings
============

Shared runtime objects for the template.

Model resolution uses Agno's native `get_model` factory, which accepts
provider-prefixed IDs like ``anthropic:claude-sonnet-4-6`` or
``openai:gpt-4o``. Switch providers without code changes by setting
``DEFAULT_MODEL_ID`` in ``.env``.
"""

from __future__ import annotations

from os import getenv
from typing import Any

from agno.models.utils import get_model as _agno_get_model

DEFAULT_MODEL_ID = "anthropic:claude-sonnet-4-6"


def default_model() -> Any:
    """Fresh model instance per agent — avoids shared-state footguns.

    Override via ``DEFAULT_MODEL_ID=provider:id`` in ``.env``. Examples:
        DEFAULT_MODEL_ID=anthropic:claude-sonnet-4-6   # default
        DEFAULT_MODEL_ID=openai:gpt-4o
        DEFAULT_MODEL_ID=google:gemini-2.0-flash
        DEFAULT_MODEL_ID=groq:llama-3.3-70b-versatile
    """
    return _agno_get_model(model=getenv("DEFAULT_MODEL_ID", DEFAULT_MODEL_ID))
