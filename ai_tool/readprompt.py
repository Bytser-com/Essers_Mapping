"""Ask Gemini for JSON mapping proposals. No local files are sent directly."""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
import httpx

ROOT = Path(__file__).resolve().parent

FIELD_SCHEMA = {
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


def run_gemini(source_fields: list[dict], target_fields: list[dict],
               reference_examples: list[dict]) -> list[dict]:
    load_dotenv(ROOT / '.env')
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        raise ValueError('GEMINI_API_KEY not configured in .env')
    model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    try:
        timeout_ms = int(os.getenv('GEMINI_TIMEOUT_MS', '120000'))
    except ValueError as error:
        raise ValueError('GEMINI_TIMEOUT_MS must be a positive integer in milliseconds') from error
    if timeout_ms < 1:
        raise ValueError('GEMINI_TIMEOUT_MS must be a positive integer in milliseconds')
    instructions = (ROOT / 'prompt.txt').read_text(encoding='utf-8')
    payload = {
        'source_inventory': source_fields,
        'target_fields_to_map': target_fields,
        'verified_reference_examples': reference_examples,
    }
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        for attempt in range(2):
            try:
                print(f'Gemini request: {model} (attempt {attempt + 1}/2)')
                response = client.models.generate_content(
                    model=model,
                    contents=instructions + '\n\nINPUT DATA:\n' + json.dumps(payload, ensure_ascii=False),
                    config=types.GenerateContentConfig(
                        response_mime_type='application/json',
                        response_json_schema=FIELD_SCHEMA,
                        temperature=0.1,
                    ),
                )
                if not response.text:
                    raise RuntimeError('Gemini returned no text')
                parsed = json.loads(response.text)
                if not isinstance(parsed, dict) or not isinstance(parsed.get('mappings'), list):
                    raise ValueError('Gemini response did not contain a mappings list')
                return parsed['mappings']
            except errors.ServerError as error:
                if getattr(error, 'code', None) != 503 or attempt == 1:
                    raise
                print('Gemini busy (503); retrying once in 1 second...')
                time.sleep(1)
            except httpx.TimeoutException as error:
                raise RuntimeError(f'Gemini request timed out ({timeout_ms / 1000:g} seconds)') from error
    finally:
        client.close()
