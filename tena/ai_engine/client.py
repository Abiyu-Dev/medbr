import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Transient upstream errors (503 overload, 429 rate limit) are worth a short
# automatic retry — Google recommends backing off and retrying these.
_TRANSIENT_MARKERS = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded")
_RETRY_DELAYS = (2, 5)


class AIServiceUnavailable(Exception):
    """Gemini is not configured, timed out, or returned a transport error."""


class AIInvalidOutput(Exception):
    """Gemini responded but the payload could not be parsed as the schema."""


def _build_client():
    if not settings.GEMINI_API_KEY:
        raise AIServiceUnavailable("GEMINI_API_KEY is not configured.")

    from google import genai
    from google.genai import types

    timeout_ms = int(settings.GEMINI_TIMEOUT_SECONDS * 1000)
    try:
        return genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
    except TypeError:
        # Older/newer SDK builds may not accept http_options here.
        return genai.Client(api_key=settings.GEMINI_API_KEY)


def generate_structured(*, system_instruction, prompt, schema):
    """
    Call Gemini and return an instance of `schema`.
    Raises AIServiceUnavailable or AIInvalidOutput — callers never see SDK types.
    """
    from google.genai import types

    try:
        client = _build_client()
    except AIServiceUnavailable:
        raise
    except Exception as exc:  # pragma: no cover - SDK import/config edge cases
        logger.warning("Gemini client init failed: %s", exc)
        raise AIServiceUnavailable("Gemini client could not be initialized.")

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.2,
    )

    try:
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
                break
            except Exception as exc:
                text = str(exc)
                transient = any(m in text for m in _TRANSIENT_MARKERS)
                if not transient or attempt == len(_RETRY_DELAYS):
                    raise
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "Gemini transient error (%s), retrying in %ss: %s",
                    attempt + 1,
                    delay,
                    text[:200],
                )
                time.sleep(delay)
    except Exception as exc:
        logger.warning("Gemini call failed: %s", exc)
        raise AIServiceUnavailable("Gemini request failed or timed out.")

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, schema):
            return parsed
        try:
            return schema.model_validate(parsed)
        except Exception as exc:
            raise AIInvalidOutput(f"Response did not match schema: {exc}")

    text = getattr(response, "text", None)
    if not text:
        raise AIInvalidOutput("Gemini returned an empty response.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIInvalidOutput(f"Gemini returned non-JSON output: {exc}")

    try:
        return schema.model_validate(data)
    except Exception as exc:
        raise AIInvalidOutput(f"Response did not match schema: {exc}")