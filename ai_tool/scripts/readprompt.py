"""Gemini transport for quality-first, direct raw-XML mapping proposals.

XML examples are transmitted as their original XML text (not a flattened JSON
conversion). The model's response alone is structured JSON for review/export.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from pathlib import Path
from typing import Callable

import httpx
from dotenv import load_dotenv
try:
    from google import genai
    from google.genai import errors, types
except ImportError:  # Preview/offline modes work before installing API dependencies.
    genai = errors = types = None

ROOT = Path(__file__).resolve().parent.parent

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
                    'rule_type': {
                        'type': 'string',
                        'enum': [
                            'DIRECT', 'FIXED', 'DEFAULT_IF_EMPTY', 'DERIVED',
                            'CONDITIONAL', 'LOOKUP', 'LOOP', 'FORMAT_DATE',
                            'REVIEW_REQUIRED', 'NOT_MAPPED',
                        ],
                    },
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
    instructions = (ROOT / 'prompt.txt').read_text(encoding='utf-8')
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
        raise RuntimeError('google-genai is not installed. Run: python -m pip install -r requirements.txt')
    load_dotenv(ROOT / '.env')
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        raise ValueError('GEMINI_API_KEY is not configured in .env')
    model = model or os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    contents = build_mapping_contents(
        source_fields, target_fields, all_target_fields or target_fields,
        source_documents or [], historical_pairs or [], reference_examples,
    )
    print(f'Raw customer XMLs in request: {len(source_documents or [])}')
    print(f'Raw historical conversion pairs in request: {len(historical_pairs or [])}')
    print(f'Prompt size: {len(contents):,} characters')

    timeout = int(os.getenv('GEMINI_TIMEOUT_MS', '120000'))
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
                print(f'Gemini request: {model} (attempt {attempt}/4)')
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
                    print(f'Input tokens: {usage.prompt_token_count}')
                    print(f'Output tokens: {usage.candidates_token_count}')
                    print(f'Total tokens: {usage.total_token_count}')
                    if on_event:
                        on_event({
                            'type': 'usage',
                            'input_tokens': usage.prompt_token_count,
                            'output_tokens': usage.candidates_token_count,
                            'total_tokens': usage.total_token_count,
                        })
                if not response.text:
                    raise RuntimeError('Gemini returned no text')
                result = json.loads(response.text)
                if not isinstance(result, dict) or not isinstance(result.get('mappings'), list):
                    raise ValueError('Gemini response did not contain a mappings list')
                return result['mappings']
            except errors.ClientError as error:
                if on_event:
                    on_event({'type': 'api_error', 'code': getattr(error, 'code', None)})
                if getattr(error, 'code', None) != 429:
                    raise
                kind = _quota_type(error)
                if kind != 'minute' or attempt == 4:
                    print(f'Gemini rate limit ({kind}); existing checkpoints are safe.')
                    raise
                delay = (_retry_after_seconds(error) or 65.0) + 2.0
                print(f'Per-minute quota reached. Waiting {delay:.1f}s before retrying...')
                if on_event:
                    on_event({'type': 'retry'})
                time.sleep(delay)
            except errors.ServerError as error:
                if on_event:
                    on_event({'type': 'api_error', 'code': getattr(error, 'code', None)})
                if getattr(error, 'code', None) != 503 or attempt == 4:
                    raise
                delay = min(2 ** (attempt - 1) + random.uniform(0, 1), 30)
                print(f'Gemini overloaded (503). Retrying in {delay:.1f}s...')
                if on_event:
                    on_event({'type': 'retry'})
                time.sleep(delay)
            except httpx.TimeoutException as error:
                if on_event:
                    on_event({'type': 'api_error', 'code': 'timeout'})
                raise RuntimeError(f'Gemini request timed out ({timeout} ms)') from error
    finally:
        client.close()
