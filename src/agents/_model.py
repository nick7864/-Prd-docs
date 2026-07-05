"""Model factory: switch the LLM provider via environment variables.

Default is Gemini (no env needed) so the existing Google-course narrative and
behavior are preserved. Set the ``TRIAGE_MODEL_*`` variables to route all five
agents through any OpenAI-compatible endpoint (e.g. GLM via Zhipu's
OpenAI-compatible API, OpenAI itself, or a local model server).

Env variables
-------------
* ``TRIAGE_MODEL_PROVIDER`` — ``gemini`` (default) or ``openai_compat``.
* ``TRIAGE_MODEL`` — model name. For ``gemini``: a Gemini model string
  (default ``gemini-2.5-flash``). For ``openai_compat``: the LiteLLM model
  string; a bare name (``glm-5.2``) is auto-prefixed with ``openai/`` so
  LiteLLM routes it through the OpenAI-compatible protocol.
* ``TRIAGE_API_BASE`` — base URL of the OpenAI-compatible endpoint.
* ``TRIAGE_API_KEY`` — API key. Also accepts the common aliases
  ``ZHIPUAI_API_KEY`` / ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``.

Import-safety: ``build_model()`` is called at agent-module import time, so it
never raises. If ``openai_compat`` is requested but the config is incomplete,
it logs a warning and falls back to Gemini so the app still starts; the
pipeline's key gate then decides whether the LLM stage runs.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("prd-triage-agent.model")

GEMINI = "gemini"
OPENAI_COMPAT = "openai_compat"

_OPENAI_COMPAT_KEY_ALIASES = (
    "TRIAGE_API_KEY",
    "ZHIPUAI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def current_provider() -> str:
    """The provider the user REQUESTED (before fallback)."""
    return os.getenv("TRIAGE_MODEL_PROVIDER", GEMINI).strip().lower()


def _openai_compat_key() -> str | None:
    for name in _OPENAI_COMPAT_KEY_ALIASES:
        value = os.getenv(name)
        if value:
            return value
    return None


def _openai_compat_configured() -> bool:
    return bool(
        _openai_compat_key()
        and os.getenv("TRIAGE_MODEL")
        and os.getenv("TRIAGE_API_BASE")
    )


def _resolved_provider() -> str:
    """The provider that will ACTUALLY be used (openai_compat falls back to
    gemini when its config is incomplete)."""
    if current_provider() == OPENAI_COMPAT:
        if _openai_compat_configured():
            return OPENAI_COMPAT
        log.warning(
            "TRIAGE_MODEL_PROVIDER=openai_compat but TRIAGE_MODEL/"
            "TRIAGE_API_BASE/TRIAGE_API_KEY are incomplete; falling back to "
            "Gemini. Set all three to use the OpenAI-compatible endpoint."
        )
        return GEMINI
    return GEMINI


def build_model():
    """Return the model object for agents.

    A Gemini model string by default, or a ``LiteLlm`` wrapper for an
    OpenAI-compatible endpoint. Never raises.
    """
    if _resolved_provider() == OPENAI_COMPAT:
        from google.adk.models.lite_llm import LiteLlm

        model = os.environ["TRIAGE_MODEL"]
        if "/" not in model:
            model = f"openai/{model}"
        return LiteLlm(
            model=model,
            api_base=os.environ["TRIAGE_API_BASE"],
            api_key=_openai_compat_key(),
        )
    if current_provider() == GEMINI:
        return os.getenv("TRIAGE_MODEL", "gemini-2.5-flash")
    return "gemini-2.5-flash"


def _has_model_key() -> bool:
    """Whether the API key for the RESOLVED provider is present.

    Used by the orchestrator to decide whether the LLM stage can run.
    """
    if _resolved_provider() == OPENAI_COMPAT:
        return True
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
