"""Small Gemini-based quality gate for a single uploaded mapping workbook."""

from __future__ import annotations

import json
import os
from pathlib import Path

from excel_review import simple_stats

PROMPT_PATH = Path(__file__).with_name('review_prompt.txt')

RESPONSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'decision': {'type': 'string', 'enum': ['ACCEPTED', 'REJECTED']},
        'summary': {'type': 'string'},
        'findings': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['decision', 'summary', 'findings'],
    'additionalProperties': False,
}


class ReviewUnavailable(RuntimeError):
    """A trustworthy AI review result could not be obtained."""


def review_with_gemini(records: list[dict]) -> dict:
    """Send ONLY Excel-derived mapping fields to Gemini and validate its response."""
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    # Load the shared .env from the repository root.
    ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(ROOT / '.env')

    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    model = (os.getenv('GEMINI_REVIEW_MODEL') or os.getenv('GEMINI_MODEL') or '').strip()
    if not api_key or not model:
        raise ReviewUnavailable('Configure GEMINI_API_KEY and GEMINI_REVIEW_MODEL (or GEMINI_MODEL).')

    payload = json.dumps({'summary': simple_stats(records), 'mappings': records}, ensure_ascii=False)
    prompt = PROMPT_PATH.read_text(encoding='utf-8')
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60000))
    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt, payload],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type='application/json',
                response_json_schema=RESPONSE_SCHEMA,
            ),
        )
        if not response.text:
            raise ReviewUnavailable('Gemini returned no review result.')
        result = json.loads(response.text)
        if not isinstance(result, dict) or result.get('decision') not in {'ACCEPTED', 'REJECTED'}:
            raise ReviewUnavailable('Gemini returned an invalid decision.')
        if not isinstance(result.get('summary'), str) or not isinstance(result.get('findings'), list):
            raise ReviewUnavailable('Gemini returned an invalid review format.')
        if any(not isinstance(finding, str) for finding in result['findings']):
            raise ReviewUnavailable('Gemini returned invalid findings.')
        if result['decision'] == 'REJECTED' and not result['findings']:
            raise ReviewUnavailable('Gemini rejected the workbook without explaining why.')
        return {
            'decision': result['decision'],
            'summary': result['summary'][:600],
            'findings': [finding[:300] for finding in result['findings'][:5]],
            'checked_mappings': len(records),
        }
    except (json.JSONDecodeError, ValueError) as error:
        raise ReviewUnavailable('Unable to parse the Gemini review result.') from error
    finally:
        client.close()
