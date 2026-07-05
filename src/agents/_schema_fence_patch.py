"""Strip fences + repair malformed JSON before ADK schema validation.

Why this exists
---------------
Models routed through LiteLLM via OpenAI-compatible endpoints (e.g. GLM via
Zhipu) do not honour ``output_schema`` as strictly as Gemini's native
structured output. Observed failure modes:

1. **Markdown fences** — output wrapped in `````json ... ````` even though a
   schema is set. ADK's ``validate_schema`` calls ``model_validate_json``
   directly and rejects the leading backticks.
2. **Prose around JSON** — the model emits explanatory text before/after the
   JSON object (``"# RiskReport — PRD-001\\n{...}"``), so the payload is not
   pure JSON.
3. **Structurally malformed JSON** — missing commas/colons, trailing commas,
   unescaped characters (``"{\\"a\\": 1 b: 2}"``). Valid JSON envelope but a
   syntax error inside.

All three are common with non-Gemini providers and bite exactly the
multi-model path. Gemini's native structured output returns clean JSON, so
the Gemini path is unaffected.

What it does
------------
Wraps ``validate_schema`` with a three-stage pipeline:

1. **Strip fences** — remove a surrounding `````json````` / ````` `` pair.
2. **Delegate** to ADK's original validator. Success → return.
3. **Recover** — extract the outermost ``{...}`` substring (handles prose-
   wrapped JSON) and run ``json-repair`` on it (fixes missing commas/colons,
   trailing commas, unescaped chars), then re-validate. Success → return.

Any still-failing validation is logged and returns ``None`` (non-fatal), so
ADK stores ``None`` under the agent's ``output_key`` and the orchestrator's
existing graceful-degradation path treats that agent as "no output".

Patch surface
-------------
``llm_agent.py`` binds ``validate_schema`` via ``from ... import validate_schema``
at import time, so we reassign BOTH ``_schema_utils.validate_schema`` and
``llm_agent.validate_schema`` (the name actually called in
``__maybe_save_output_to_state``).
"""
from __future__ import annotations

import logging
import re

from google.adk.agents import llm_agent
from google.adk.utils import _schema_utils
from json_repair import repair_json

log = logging.getLogger("prd-triage-agent.schema")

# Matches a whole-string markdown fence:
#   ```json\n{...}\n```   or   ```\n{...}\n```   (any optional language tag)
_FENCE_RE = re.compile(
    r"^\s*```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)

# Greedy match from the first '{' to the last '}' — extracts the outermost
# JSON object even when the model wraps it in prose/Markdown.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

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


def _extract_json_object(text):
    """Return the outermost ``{...}`` substring, or ``None`` if no brace pair.

    Used to lift a JSON payload out of surrounding prose/Markdown so
    ``json-repair`` can operate on just the object.
    """
    if not isinstance(text, str):
        return None
    match = _JSON_OBJECT_RE.search(text)
    if match:
        return match.group(0)
    return None


def _repair_json_text(text):
    """Best-effort recovery of a malformed JSON object via ``json-repair``.

    Extracts the outermost ``{...}`` (so prose-wrapped payloads are handled)
    and runs ``repair_json`` to fix common syntax errors: missing
    commas/colons, trailing commas, unescaped characters. Returns the
    repaired JSON string, or ``None`` when no ``{...}`` can be found (e.g.
    the model emitted pure Markdown with no JSON at all — unrecoverable).
    """
    candidate = _extract_json_object(text)
    if candidate is None:
        return None
    try:
        return repair_json(candidate, return_objects=False)
    except Exception:  # noqa: BLE001 — repair is best-effort
        return None


def validate_schema(schema, json_text):
    """Fence-strip + json-repair + non-fatal shim around ADK's validator.

    Pipeline: strip fences → validate → (on failure) extract & repair →
    re-validate. Any still-failing validation is logged and returns ``None``
    so the orchestrator degrades gracefully (treats the agent as "no output")
    instead of crashing the triage.
    """
    cleaned = _strip_fences(json_text)
    try:
        return _original_validate_schema(schema, cleaned)
    except Exception:
        pass  # handled by the recovery path below

    repaired = _repair_json_text(cleaned)
    if repaired is None:
        name = getattr(schema, "__name__", None) or repr(schema)
        log.warning(
            "validate_schema failed for %s; no recoverable JSON found "
            "(graceful degradation). Input was: %.120r", name, cleaned
        )
        return None
    try:
        return _original_validate_schema(schema, repaired)
    except Exception as exc:  # noqa: BLE001 — repaired output still invalid
        name = getattr(schema, "__name__", None) or repr(schema)
        log.warning(
            "validate_schema failed for %s even after json-repair; treating "
            "its output as absent (graceful degradation). Parser error: %s",
            name, exc,
        )
        return None


# Reassign on both the source module and llm_agent's already-imported alias.
_schema_utils.validate_schema = validate_schema
llm_agent.validate_schema = validate_schema
