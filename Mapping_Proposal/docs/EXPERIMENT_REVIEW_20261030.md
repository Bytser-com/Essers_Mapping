# Review of the 96-target Nouryon run (2026-10-30)

Source files: `history3_source5_targets96_01e342ad.zip` and experiment
`20261030T131739_dc89f5e9.json`. This review refers to the **old** run;
the update below only affects future runs.

## Observed results

- 96 target mappings, zero rejected proposals, one structural validation issue.
- 66 DIRECT, 10 CONDITIONAL, 8 NOT_MAPPED, 4 REVIEW_REQUIRED,
  4 LOOP, 2 DEFAULT_IF_EMPTY, 1 LOOKUP, 1 DERIVED.
- 19 DIRECT mappings also have loop instructions. This is not automatically
  contradictory: copying an item value and repeating the target item are distinct
  operations. Review loop context where parent/child alignment matters.
- Only three Nouryon source XMLs were transmitted, despite requesting five,
  because of the raw-source character budget.
- 84 exact-value historical observations were extracted. Exact matches alone do
  not establish business-correct mappings.
- Structural issue: target `.../E1BPDLVDEADLN/@SEGMENT` used source
  `/DELVRY03/IDOC/E1EDL20/E1EDT13` (a parent segment, not a listed field).
  Keep the strict path validation; verify the segment-generation rule and use
  an actual attribute path if appropriate.
- Risk severity values are inconsistent (LOW, MEDIUM, HIGH, Low, Medium,
  High, NONE, DATA_INTEGRITY, BUSINESS_LOGIC, COMPLIANCE). The schema previously
  allowed any string.
- The experiment recorded 404,609 input tokens and 408,150 total tokens,
  but it restored eight of ten checkpoints. Those totals describe only the
  final execution, not all ten batches. Checkpoints from this run contain
  targets, signature and proposals, but no usage metadata.

## Focused fix

1. `mapping_schema.json` constrains `risk_category` to LOW, MEDIUM or HIGH.
2. `prompt.txt` explains risk *severity* versus risk *kind*, and technical
   target attributes versus segment paths.
3. `mapping_validator.py` normalizes casing and flags unsupported risk values
   for expert review rather than quietly accepting an invalid category.
4. `experiment_tracker.py` writes `output/runs/<job>/usage_ledger.json`
   immediately when the Gemini helper reports usage, attempts or errors.
5. `pipeline.py` includes API usage metrics in each **new** batch checkpoint.
   On resume, cumulative usage is read from the durable ledger, or recovered
   from checkpoint metrics when the ledger is missing.
6. The global experiment CSV/JSON separates cumulative job tokens from
   per-execution tokens. The CSV header is upgraded automatically while
   preserving previously logged rows.

## Important limits

- No live Gemini API request was performed when testing this patch.
- Failed API requests that do not return `usage_metadata` cannot be counted
  exactly; the token fields represent **API-reported** usage, not necessarily
  provider-billed total tokens.
- The **previous** eight checkpoints cannot provide historical token counts:
  they never saved them. If older failed/interrupted experiment records remain
  in `output/experiments/`, their recorded token totals can be summed by
  run_folder as a historical estimate. Do not rewrite old logs as exact.
- This code update changes the code fingerprint: it will create a NEW run
  signature/directory, rather than resuming old checkpoints from the 96-target run.
- The risk-severity normalization does **not** prove mapping correctness.
