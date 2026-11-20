# Mapping Converter — Excel consistency check (prototype)

This update adds an **Excel-only Gemini consistency check**. It does not yet
convert or execute mappings, write to SFTP, or modify the frontend.

## Setup

From `Mapping_Converter/`:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure `GEMINI_API_KEY` and
`GEMINI_REVIEW_MODEL` (a valid model for your API access).

Start:

```bash
python -m uvicorn api:app --reload --port 8001
```

Swagger UI: <http://localhost:8001/docs>

## Review an uploaded Excel file

```bash
curl -F "file=@mapping_package.xlsx" http://localhost:8001/review-excel
```

The frontend/Java backend can send its uploaded `.xlsx` to this endpoint as a
multipart request (`file` field) **before** accepting or publishing a package.
Only publish/process the workbook if `decision == "ACCEPTED"`.

Example response:

```json
{
  "decision": "REJECTED",
  "summary": "A direct mapping is missing a source.",
  "findings": ["Row 3: DIRECT has no source path."],
  "checked_mappings": 96
}
```

- `200` + `ACCEPTED`: AI found no obvious inconsistencies.
- `200` + `REJECTED`: AI found clear problems; show the reasons to the user.
- `400/422`: upload or workbook structure invalid; do not accept.
- `503`: missing configuration, AI unavailable, or invalid model response;
  **do not accept** and optionally offer a retry.

The model only receives selected columns from the **uploaded Excel file**;
no historical XML pairs, Gemini proposal prompt, or SFTP files are read.
It is still a **cloud AI call**: ensure uploaded workbooks may legally be sent
to the selected provider (anonymize sensitive data where necessary).

Review is a lightweight *consistency* check, not a proof of correct business
mappings. The output should not be treated as a substitute for specialist signoff.

## Tests

```bash
python -m pytest -q
python -m ruff check .
```

No live Gemini request is made by the unit tests.
