"""Strip markdown code fences from model output before ADK schema validation.

Why this exists
---------------
Models routed through LiteLLM via OpenAI-compatible endpoints (e.g. GLM via
Zhipu) often wrap structured JSON output in `````json ... ````` fences, even
when ``output_schema`` is set. ADK's ``validate_schema`` calls
``model_validate_json`` directly and rejects the leading backticks with::

    pydantic_core.ValidationError: Invalid JSON: expected value at line 1 column 1

Gemini's native structured output returns clean JSON, so this only bites
non-Gemini providers — which is exactly the multi-model path.

What it does
------------
Wraps ``validate_schema`` to strip a leading `````json`` / ````` `` fence and
trailing ````` `` before delegating to ADK's original implementation. It is a
no-op for already-clean JSON (Gemini path unaffected) and idempotent.

Patch surface
-------------
``llm_agent.py`` binds ``validate_schema`` via ``from ... import validate_schema``
at import time, so we reassign BOTH ``_schema_utils.validate_schema`` and
``llm_agent.validate_schema`` (the name actually called in ``__maybe_save_output_to_state``).
"""
from __future__ import annotations

import logging
import re

from google.adk.agents import llm_agent
from google.adk.utils import _schema_utils

log = logging.getLogger("prd-triage-agent.schema")

# Matches a whole-string markdown fence:
#   ```json\n{...}\n```   or   ```\n{...}\n```   (any optional language tag)
_FENCE_RE = re.compile(
    r"^\s*```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)

_original_validate_schema = _schema_utils.validate_schema


def _strip_fences(json_text):
    """Return json_text with a surrounding markdown code fence removed.

    Non-str input and already-clean JSON are returned unchanged.
    """
    if isinstance(json_text, str):
        match = _FENCE_RE.match(json_text.strip())
        if match:
            return match.group(1).strip()
    return json_text


def validate_schema(schema, json_text):
    """Fence-stripping + non-fatal shim around ADK's validator.

    Strips markdown fences (non-Gemini providers like GLM wrap JSON in
    `````json`````), then delegates. If validation still fails (the model
    produced structurally invalid JSON — also common with non-Gemini models),
    log a warning and return ``None`` instead of raising. ADK then stores
    ``None`` under the agent's ``output_key`` and the orchestrator's existing
    graceful-degradation path treats that agent as "no output": synthesis
    falls back to deterministic assembly, a specialist is treated as absent.
    This keeps a single malformed agent output from crashing the whole triage.
    """
    cleaned = _strip_fences(json_text)
    try:
        return _original_validate_schema(schema, cleaned)
    except Exception as exc:  # noqa: BLE001 — any validation failure → degrade
        name = getattr(schema, "__name__", None) or repr(schema)
        log.warning(
            "validate_schema failed for %s; treating its output as absent "
            "(graceful degradation). Parser error: %s", name, exc
        )
        return None


# Reassign on both the source module and llm_agent's already-imported alias.
_schema_utils.validate_schema = validate_schema
llm_agent.validate_schema = validate_schema
