# Essers XML Mapping Prototype (v0.1)

This is an **AI-assisted mapping proposal generator**. It inventories XML leaf fields, asks Gemini to propose source-to-target mappings, validates basic structure, and writes an `.xlsx` review workbook based on the supplied **Mapping_Review_Nouryon_Outbound.xlsx** layout. Its suggestions are **not** approved mapping rules or executable transformations.

## Quick start (Windows PowerShell / VS Code)

From the project folder:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Test everything except the API call** using the included toy XML files and illustrative mappings:

```powershell
.\.venv\Scripts\python.exe main.py --offline
```

This creates `output/mapping_package.xlsx`, `output/mapping_proposals.json`, `output/validation_issues.json`, and `output/rejected_proposals.json`.

## Live Gemini run

1. Put your **current source XMLs** in `data/source/`.
2. Put one or more **target example XMLs** showing the desired structure in `data/target/`. An XSD-only target is **not supported yet**.
3. Remove the bundled toy XMLs from those folders so they don't contaminate your inventories.
4. Copy `.env.example` to `.env` and set your own API key and model. **Never commit `.env`**.
   Gemini HTTP requests have a 120-second timeout by default. To change it, add
   `GEMINI_TIMEOUT_MS=180000` to `.env` (the value is in milliseconds).
5. Optionally create `data/reference/verified_mappings.json` using the format of `verified_mappings.example.json`. Only include truly approved historical mappings. The bundled example is *not* verified evidence.
6. Run:

```powershell
.\.venv\Scripts\python.exe main.py --limit-targets 10
```

This requests proposals for the first **10 target leaf fields**, sorted by path. It makes **one Gemini call** by default. Once this works, try `--limit-targets 20`, or `--limit-targets 0` for all targets. The `--batch-size` argument controls requests per batch; each call can consume quota.

## Directory layout

```text
main.py                     Pipeline entry point
xml_parser.py               XML field extraction (ElementTree)
readprompt.py               Gemini JSON response + configurable 120 s timeout and 503 retry
mapping_validator.py        Structural validation of AI proposals
excel_generator.py          Excel output using original workbook layout
prompt.txt                  Editable AI instructions
requirements.txt            Python packages
.env.example                API settings template (no secrets)
data/source/                Source XML documents
  example_delivery.xml      Toy XML for --offline
data/target/                Target XML examples
  example_target.xml         Toy XML for --offline
data/reference/             Optional verified mapping examples
  verified_mappings.example.json   Example format only
  demo_proposals.json       Toy offline output, not approved evidence
templates/
  mapping_template.xlsx     Existing workbook layout; contains historical *example content*
output/                     Generated reports (Git-ignored)
```

## What the pipeline does

1. Extracts XML leaf paths, occurrence counts, source filenames, and up to three sample values per path.
2. Sends the source inventory, a batch of target paths, and any manually added verified examples to Gemini.
3. Requests structured JSON mapping proposals (direct, fixed, conditional, lookup, etc.). The AI is explicitly asked **not to invent paths or constants**.
4. Validates returned paths and flags source-path mismatches; rejects proposals for nonexistent targets.
5. Reuses the uploaded eight-tab workbook layout but clears previous customer-specific rows before writing. Populates **Mapping Proposal**, **Review Questions**, **Runtime Field Inventory**, **File Classification**, and **Summary**. **Rule Types** is retained; **Reference Evidence** and **Assumptions & Risks** are intentionally left unpopulated until actual evidence/risk generation is implemented.
6. Saves both the review workbook and machine-readable JSON files.

## Important limitations / next steps

- **Proof of concept only**: source-to-target semantic correctness is **not proven** by path validation.
- The target parser needs a **representative target XML**. A full XSD parser is a later task.
- Verified reference mapping pairs (`*_Original.xml`, `*_Converted.xml`) are **not automatically learned yet**. For now, curated `verified_mappings.json` examples are supported.
- XML namespaces are stripped for path comparison; same-name elements across distinct namespaces may collide.
- Leaf-only inventory doesn't capture full loop hierarchy or cardinality; repetitive structures need review.
- Gemini's confidence score is **subjective**, not measured accuracy.
- The example workbook originally contains customer-specific historical rows; generation clears those rows in the output file. The template on disk is unchanged.
- The offline data is toy data to verify the plumbing, **not a verified mapping**.
- A matching current input/target corpus and approved examples should be used before evaluating accuracy. Keep benchmark/ground-truth examples separate from prompts where practical.

## Team review checklist

Check each high-impact mapping for semantic correctness, qualifiers, date formats, partner roles, quantity rules, fixed control values, and loop boundaries. The output is a review document; human approval remains required.

## Unit tests (no Gemini requests)

```powershell
.\.venv\Scripts\python.exe -m unittest test_core.py
```
