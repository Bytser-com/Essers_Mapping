# Mapping Converter — Excel consistency review (prototype)

This service accepts a mapping workbook and uses Gemini to assess obvious
internal inconsistencies. It does **not** execute mappings, access historical
XML, write to SFTP, or intercept frontend uploads yet.

## Architecture

- `api.py` — FastAPI routes, upload validation and HTTP responses.
- `scripts/pipeline.py` — Coordinates Excel extraction followed by AI review.
- `scripts/excel_review.py` — Extracts mapping fields from uploaded XLSX files.
- `scripts/gemini_review.py` — Calls Gemini and validates its JSON response.
- `scripts/config.py` — Reads settings from the shared **repository-root `.env`**
  locally (environment variables override it).
- `review_prompt.txt` — Instructions for Gemini's accept/reject decision.
- `tests/` — Local endpoint and extraction tests; no live Gemini calls.

The public API and response format are unchanged by this refactor.

## Setup (from `Mapping_Converter/`)

```bash
python -m pip install -r requirements.txt
```

Store `GEMINI_API_KEY` and `GEMINI_REVIEW_MODEL` (or `GEMINI_MODEL`) in the
**Essers_Mapping repository-root `.env`**, or provide them as environment
variables. `.env.example` lists the variables; do not commit API keys.

```bash
python -m uvicorn api:app --reload --port 8001
```

Swagger: http://localhost:8001/docs

## Review an Excel file

```bash
curl -F "file=@mapping_package.xlsx" http://localhost:8001/review-excel
```

A successful review request returns HTTP 200 and a JSON `decision` of
`ACCEPTED` or `REJECTED`, along with `summary`, `findings`, and
`checked_mappings`. HTTP 400/422 means an invalid upload/workbook; HTTP 503
means the AI review is unavailable. **Neither is an acceptance.**

The frontend/Java service must integrate this endpoint before publishing
any reviewed package. Only a result with `decision == "ACCEPTED"` should
proceed; the service does not currently implement that integration.

Only Excel-derived mapping fields are sent to Gemini. A human specialist
still needs to verify business correctness. Confirm that uploaded workbook
content is permitted to leave your environment for the AI provider.

## Tests

```bash
python -m pytest -q
python -m ruff check .
```
