"""Gemini transport for quality-first, direct raw-XML mapping proposals.

XML examples are transmitted as their original XML text (not a flattened JSON
conversion). The model's response alone is structured JSON for review/export.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Callable

import httpx
try:
    from google import genai
    from google.genai import errors, types
except ImportError:  # Preview/offline modes work before installing API dependencies.
    genai = errors = types = None

# Settings (API key, model, timeout) now come from config.py instead of
# reading .env here; errors are translated into the tool's own error types.
from .config import PROMPT_PATH, load_settings
from .errors import ConfigError, GeminiError, QuotaExceededError

logger = logging.getLogger(__name__)

RULE_SCHEMA = {
    'type': 'object',
    'properties': {
        'mappings': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'source_path': {'type': 'string'},
                    'target_path': {'type': 'string'},
                    'rule_type': {'type': 'string'},
                    'confidence': {'type': 'integer'},
                    'requires_review': {'type': 'boolean'},
                    'review_priority': {'type': 'string'},
                    'reason': {'type': 'string'},
                    'evidence': {'type': 'string'},
                    'fixed_value': {'type': 'string'},
                    'transformation': {'type': 'string'},
                    'condition': {'type': 'string'},
                    'lookup': {'type': 'string'},
                    'loop': {'type': 'string'},
                    'review_question': {'type': 'string'},
                    'risk_category': {'type': 'string'},
                },
                'required': [
                    'source_path', 'target_path', 'rule_type', 'confidence',
                    'requires_review', 'review_priority', 'reason', 'evidence',
                    'fixed_value', 'transformation', 'condition', 'lookup',
                    'loop', 'review_question', 'risk_category',
                ],
            },
        },
    },
    'required': ['mappings'],
}


def _quota_type(error: Exception) -> str:
    description = str(error).lower()
    if any(term in description for term in ('perday', 'per_day', 'per-day', 'requests per day', 'daily quota', 'rpd')):
        return 'daily'
    if any(term in description for term in ('perminute', 'per_minute', 'per-minute', 'per minute', 'tpm', 'rpm')):
        return 'minute'
    return 'unknown'


def _retry_after_seconds(error: Exception) -> float | None:
    description = str(error)
    for pattern in (
        r'Please retry in\s+([0-9]+(?:\.[0-9]+)?)s',
        r'[\'\"]retryDelay[\'\"]\s*:\s*[\'\"]([0-9]+(?:\.[0-9]+)?)s',
    ):
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Error translation: turn Gemini's long API errors into one clear sentence.
# ---------------------------------------------------------------------------
def _short_message(error: Exception) -> str:
    """The API's own one-line message, without the full JSON payload."""
    return str(getattr(error, 'message', None) or error).splitlines()[0][:300]


def _client_error(error: Exception) -> Exception:
    """Translate a non-quota 4xx Gemini error into a clear tool error."""
    code = getattr(error, 'code', None)
    text = str(error)
    # 400 with API_KEY_INVALID: the key in .env is wrong or still the placeholder.
    if 'API_KEY_INVALID' in text or 'API key not valid' in text:
        return ConfigError('Gemini rejected the API key. Check GEMINI_API_KEY in ai_tool/.env.')
    if code in (401, 403):
        return ConfigError(f'Gemini refused access ({code}): {_short_message(error)}')
    if code == 404:
        return ConfigError(f'Gemini model not found (404). Check GEMINI_MODEL or --model: {_short_message(error)}')
    return GeminiError(f'Gemini request failed ({code}): {_short_message(error)}', code=code)


def build_mapping_contents(
    source_fields: list[dict],
    target_fields: list[dict],
    all_target_fields: list[dict],
    source_documents: list[dict],
    historical_pairs: list[dict],
    verified_examples: list[dict] | dict | None = None,
) -> str:
    """Assemble one prompt. Keeps full XML text, never pre-infers a mapping.

    File inventories are sent as compact path *indexes*: these are authoritative
    valid-path lists, not substitutes for the full raw XML examples.
    """
    instructions = PROMPT_PATH.read_text(encoding='utf-8')
    source_index = [
        {
            'path': f['path'], 'kind': f['kind'], 'count': f['count'],
            'files_count': len(f.get('files', [])), 'examples': f.get('examples', []),
        }
        for f in source_fields
    ]
    target_index = [
        {'path': f['path'], 'kind': f.get('kind', 'element'),
         'examples': f.get('examples', [])}
        for f in target_fields
    ]
    context = {
        'source_inventory_all_valid_paths': source_index,
        'common_target_inventory_all_valid_paths': [f['path'] for f in all_target_fields],
        'requested_target_fields_to_map': target_index,
        'verified_reference_examples': verified_examples or [],
    }
    chunks = [instructions, '\n\nSTRUCTURED CONTEXT (JSON indexes; not converted XML):',
              json.dumps(context, ensure_ascii=False, separators=(',', ':'))]
    chunks.append('\n\nNEW CUSTOMER ORIGINAL XML EXAMPLES (raw XML; no target result available):')
    for document in source_documents:
        chunks.extend([
            f"\n--- ORIGINAL CUSTOMER XML FILE: {document['filename']} ---\n",
            document['xml'], '\n--- END ORIGINAL CUSTOMER XML ---',
        ])
    chunks.append('\n\nHISTORICAL MATCHED CONVERSION EXAMPLES (raw XML; paired by ID):')
    for pair in historical_pairs:
        chunks.extend([
            f"\n--- HISTORICAL ORIGINAL: {pair['company']} / {pair['pair_id']} / {pair['original_filename']} ---\n",
            pair['original_xml'],
            '\n--- END HISTORICAL ORIGINAL ---',
            f"\n--- MATCHING HISTORICAL CONVERTED: {pair['company']} / {pair['pair_id']} / {pair['converted_filename']} ---\n",
            pair['converted_xml'],
            '\n--- END HISTORICAL CONVERTED ---',
        ])
    chunks.append(
        '\n\nFINAL REQUEST: Return precisely one proposal per requested target_path. '
        'Use only valid new-customer source paths; historical source paths are not valid. '
        'Do not omit uncertain targets. Produce ONLY the structured JSON response.'
    )
    return '\n'.join(chunks)


def run_gemini(
    source_fields: list[dict],
    target_fields: list[dict],
    reference_examples: list[dict] | dict | None = None,
    *,
    all_target_fields: list[dict] | None = None,
    source_documents: list[dict] | None = None,
    historical_pairs: list[dict] | None = None,
    model: str | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Propose mappings using direct raw XML context (no knowledge distillation)."""
    if genai is None:
        raise ConfigError('google-genai is not installed. Run: python -m pip install -r requirements.txt')
    # Read the API key, model and timeout from the central configuration.
    settings = load_settings()
    key = settings.gemini_api_key
    if not key:
        raise ConfigError('GEMINI_API_KEY is not configured in .env')
    model = model or settings.gemini_model
    contents = build_mapping_contents(
        source_fields, target_fields, all_target_fields or target_fields,
        source_documents or [], historical_pairs or [], reference_examples,
    )
    logger.info('Raw customer XMLs in request: %d', len(source_documents or []))
    logger.info('Raw historical conversion pairs in request: %d', len(historical_pairs or []))
    logger.info('Prompt size: %s characters', f'{len(contents):,}')

    timeout = settings.gemini_timeout_ms
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=timeout,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        for attempt in range(1, 5):
            try:
                logger.info('Gemini request: %s (attempt %d/4)', model, attempt)
                if on_event:
                    on_event({'type': 'attempt'})
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type='application/json',
                        response_json_schema=RULE_SCHEMA,
                        temperature=0.1,
                    ),
                )
                if response.usage_metadata:
                    usage = response.usage_metadata
                    logger.info('Input tokens: %s', usage.prompt_token_count)
                    logger.info('Output tokens: %s', usage.candidates_token_count)
                    logger.info('Total tokens: %s', usage.total_token_count)
                    if on_event:
                        on_event({
                            'type': 'usage',
                            'input_tokens': usage.prompt_token_count,
                            'output_tokens': usage.candidates_token_count,
                            'total_tokens': usage.total_token_count,
                        })
                if not response.text:
                    raise GeminiError('Gemini returned no text')
                try:
                    result = json.loads(response.text)
                except json.JSONDecodeError as error:
                    raise GeminiError(f'Gemini returned invalid JSON: {error}') from error
                if not isinstance(result, dict) or not isinstance(result.get('mappings'), list):
                    raise GeminiError('Gemini response did not contain a mappings list')
                return result['mappings']
            except errors.ClientError as error:
                if on_event:
                    on_event({'type': 'api_error', 'code': getattr(error, 'code', None)})
                # 429 = rate limit. Only a per-minute limit is worth waiting for;
                # a daily limit stops the run (checkpoints keep finished batches).
                code = getattr(error, 'code', None)
                if code != 429:
                    raise _client_error(error) from error
                kind = _quota_type(error)
                if kind != 'minute' or attempt == 4:
                    raise QuotaExceededError(f'Gemini rate limit reached ({kind} quota).', code=429) from error
                delay = (_retry_after_seconds(error) or 65.0) + 2.0
                logger.warning('Per-minute quota reached. Waiting %.1fs before retrying...', delay)
                if on_event:
                    on_event({'type': 'retry'})
                time.sleep(delay)
            except errors.ServerError as error:
                if on_event:
                    on_event({'type': 'api_error', 'code': getattr(error, 'code', None)})
                # 503 = Gemini overloaded: retry with increasing waits, up to 4 attempts.
                code = getattr(error, 'code', None)
                if code == 503 and attempt == 4:
                    raise QuotaExceededError('Gemini is overloaded (503).', code=503) from error
                if code != 503:
                    raise GeminiError(f'Gemini server error ({code}): {_short_message(error)}', code=code) from error
                delay = min(2 ** (attempt - 1) + random.uniform(0, 1), 30)
                logger.warning('Gemini overloaded (503). Retrying in %.1fs...', delay)
                if on_event:
                    on_event({'type': 'retry'})
                time.sleep(delay)
            except httpx.TimeoutException as error:
                if on_event:
                    on_event({'type': 'api_error', 'code': 'timeout'})
                raise GeminiError(f'Gemini request timed out ({timeout} ms)', code='timeout') from error
    finally:
        client.close()
