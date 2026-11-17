# Focused V2 fix — Risk severity and resumable token accounting

Unzip this patch into the **root of your Mapping_Proposal project**, overwriting
only the corresponding files. Back up your project first and commit to your V2
feature branch. Your `.env`, `data/`, `output/`, and existing workbooks are not
included in this patch and must remain untouched.

Changed files:
- `mapping_schema.json` — `risk_category` enum: `LOW`, `MEDIUM`, `HIGH`.
- `prompt.txt` — instructions for risk severity and technical segment paths.
- `scripts/mapping_validator.py` — normalize risk values, flag unsupported ones.
- `scripts/experiment_tracker.py` — durable usage ledger, full-job/per-execution
  token counts, CSV migration.
- `scripts/pipeline.py` — per-batch checkpoint metadata and ledger restoration.
- `tests/unit/test_resumable_usage.py` — offline regression tests.

Run tests:

```powershell
python -m unittest discover -s tests/unit -p "test_resumable_usage.py" -v
python main.py --preview --history-pairs 3 --source-samples 5 --limit-targets 0
```

A future run writes the following metadata:

```
output/
  experiments.csv                       global record, per invocation
  experiments/<run-id>.json             detailed record
  runs/<job>/
    usage_ledger.json                    durable usage accumulated across resumes
    checkpoints/batch_0001.json         includes proposals + batch `metrics`
    mapping_package.xlsx
```

`input_tokens` / `output_tokens` / `total_tokens` are now the **whole job's
API-reported totals**, even across resumed invocations. `execution_input_tokens`
(and equivalents) are usage in the *current* CLI execution. `duration_seconds`
is also per execution; `job_active_duration_seconds` sums recorded durations.

If you already have `output/experiments.csv`, the tracker upgrades its header
as part of the next run and keeps existing rows, with the new fields blank for
old runs. Consider backing up `output/experiments.csv` yourself before your
first new execution.

The old 96-target checkpoints have **no** token metadata and cannot be made
accurate retrospectively from their proposal files alone. This fix protects
future interrupted/resumed runs. All mapping proposals still require review.
