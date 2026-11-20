"""Small Gemini-based quality gate for a single uploaded mapping workbook."""

from __future__ import annotations

import json
import logging
import os
import random
import time

import httpx

from .config import PROMPT_PATH, load_review_settings
from .excel_review import simple_stats

logger = logging.getLogger(__name__)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["ACCEPTED", "REJECTED"]},
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "summary", "findings"],
    "additionalProperties": False,
}


class ReviewUnavailable(RuntimeError):
    """A trustworthy AI review result could not be obtained."""


def review_with_gemini(records: list[dict]) -> dict:
    """Send ONLY Excel-derived mapping fields to Gemini and validate its response."""
    from google import genai
    from google.genai import errors, types

    settings = load_review_settings()
    if not settings.api_key or not settings.model:
        raise ReviewUnavailable("Configure GEMINI_API_KEY and GEMINI_REVIEW_MODEL (or GEMINI_MODEL).")

    payload = json.dumps({"summary": simple_stats(records), "mappings": records}, ensure_ascii=False)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    client = genai.Client(
        api_key=settings.api_key,
        http_options=types.HttpOptions(timeout=settings.timeout_ms),
    )

    raw_attempts = os.getenv("GEMINI_MAX_ATTEMPTS", "5").strip()
    max_attempts = int(raw_attempts) if raw_attempts.isdigit() and int(raw_attempts) > 0 else 5

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.models.generate_content(
                    model=settings.model,
                    contents=[prompt, payload],
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        response_json_schema=RESPONSE_SCHEMA,
                    ),
                )
                if not response.text:
                    raise ReviewUnavailable("Gemini returned no review result.")
                result = json.loads(response.text)
                if not isinstance(result, dict) or result.get("decision") not in {"ACCEPTED", "REJECTED"}:
                    raise ReviewUnavailable("Gemini returned an invalid decision.")
                if not isinstance(result.get("summary"), str) or not isinstance(result.get("findings"), list):
                    raise ReviewUnavailable("Gemini returned an invalid review format.")
                if any(not isinstance(finding, str) for finding in result["findings"]):
                    raise ReviewUnavailable("Gemini returned invalid findings.")
                if result["decision"] == "REJECTED" and not result["findings"]:
                    raise ReviewUnavailable("Gemini rejected the workbook without explaining why.")
                return {
                    "decision": result["decision"],
                    "summary": result["summary"][:600],
                    "findings": [finding[:300] for finding in result["findings"][:5]],
                    "checked_mappings": len(records),
                }
            except errors.ServerError as error:
                code = getattr(error, "code", None)
                if attempt == max_attempts or code not in (500, 502, 503, 504):
                    raise ReviewUnavailable(f"Gemini server error ({code}) after {attempt} attempts: {error}") from error
                delay = min(2 ** (attempt - 1) + random.uniform(0, 1), 30)
                logger.warning(
                    "Gemini server unavailable (%s) on attempt %d/%d. Retrying in %.1fs...",
                    code, attempt, max_attempts, delay,
                )
                time.sleep(delay)
            except errors.ClientError as error:
                code = getattr(error, "code", None)
                if code == 429 and attempt < max_attempts:
                    delay = 5.0 + random.uniform(0, 2)
                    logger.warning(
                        "Gemini rate limit reached (429) on attempt %d/%d. Retrying in %.1fs...",
                        attempt, max_attempts, delay,
                    )
                    time.sleep(delay)
                else:
                    raise ReviewUnavailable(f"Gemini client error ({code}): {error}") from error
            except (httpx.TimeoutException, TimeoutError) as error:
                if attempt == max_attempts:
                    raise ReviewUnavailable(f"Gemini request timed out after {attempt} attempts: {error}") from error
                delay = min(2 ** (attempt - 1) + random.uniform(0, 1), 30)
                logger.warning(
                    "Gemini request timed out on attempt %d/%d. Retrying in %.1fs...",
                    attempt, max_attempts, delay,
                )
                time.sleep(delay)
            except (ValueError, KeyError, TypeError) as error:
                raise ReviewUnavailable(f"Unable to parse the Gemini review result: {error}") from error
    except ReviewUnavailable:
        raise
    except Exception as error:
        raise ReviewUnavailable(f"Gemini review request failed: {error}") from error
    finally:
        client.close()
