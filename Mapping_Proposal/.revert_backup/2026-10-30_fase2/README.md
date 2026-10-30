# H.Essers — AI XML Mapping Proposal (Simple Prototype)

**Goal:** Give Gemini examples of previous customer XML conversions and raw XML messages from a new customer. Gemini proposes how the new customer's data could be mapped into the common H.Essers target format. The program saves its proposals in the **existing Excel mapping template** for an integration specialist to review.

This is a **proposal generator**, not an executable XML converter. No AI proposal should be implemented without human approval.

## What happens when you run it?

1. **Python reads your data.** It finds all original XML files in `data/source/`, matches the previous customers' `Original` and `Converted` files in `data/historical/`, and lists all available source and target XML paths.
2. **Python picks complete example documents.** It chooses a small number of raw XML messages from the new customer and matched historical original/converted pairs. **It does not convert these XML documents into JSON before giving them to Gemini.**
3. **Gemini analyzes the examples.** It compares past originals with their converted versions, studies the new customer's raw XML, and proposes source paths, target paths, conditions, transformations, loops, lookups, and open questions.
4. **Python checks and exports the proposal.** It checks that the named XML paths exist and writes Gemini's structured JSON output into `mapping_package.xlsx`, preserving the supplied Excel template.

**Important:** Python scans **all** XMLs to build its field-path inventories, but Gemini receives only the **selected complete raw XML examples** plus the field-path inventories. That distinction is intentional: you can gradually increase how many real examples Gemini sees without changing the code. The model does not permanently train or remember earlier runs.

## Project folders

```text
ai_tool/
├── main.py                 Runs the complete workflow
├── prompt.txt              Explains the mapping task and rules to Gemini
├── .env.example            API key configuration example
├── requirements.txt        Python packages to install
├── scripts/
│   ├── __init__.py
│   ├── xml_parser.py       Reads XML, discovers valid paths, matches historical pairs
│   ├── readprompt.py       Builds Gemini's request; handles API calls, quota/retries
│   ├── mapping_validator.py  Flags unknown source/target paths or invalid rule types
│   └── excel_generator.py  Fills the original mapping Excel template
├── data/
│   ├── source/             Original XML files from the NEW customer (currently Nouryon)
│   └── historical/
│       ├── christeyns/    Matched *_Original.xml and *_Converted.xml
│       ├── chugoku/       Matched *_Original.xml and *_Converted.xml
│       └── hempel/        Matched *_Original.xml and *_Converted.xml
├── templates/
│   └── mapping_template.xlsx
└── output/
    ├── experiments.csv      One row per actual execution (open in Excel)
    ├── experiments/        Detailed JSON record for each execution
    │   ├── 20261029T120000_abcd1234.json
    │   └── ...
    └── runs/               Excel packages, proposals and resumable checkpoints
```

**Which files are where?** The ZIP already includes the scrambled Essers dataset: 100 Nouryon original XMLs and 400 matched historical pairs (100 Christeyns, 150 Chugoku, 150 Hempel). You do **not** need to manually split historical originals and converted files into different folders. A pair is matched by the common filename stem, e.g. `Outbound_Hempel_001_Original.xml` with `Outbound_Hempel_001_Converted.xml`.

### What each Python file does (in normal language)

| File | What it does | What it does **not** do |
|---|---|---|
| **main.py** | Finds the data, chooses how many examples to send, runs batches, and saves results | Does not decide which business fields should map |
| **scripts/xml_parser.py** | Reads XML files, remembers field paths, matches each historic original to its converted partner, selects complete examples | Does not infer mapping rules |
| **scripts/readprompt.py** | Sends the selected raw XML examples and valid path lists to Gemini; requests structured JSON; handles temporary API failures | Does not secretly train a new model |
| **scripts/mapping_validator.py** | Checks that paths and rule types are valid; flags suspicious structural output | Cannot prove a mapping is correct for Essers |
| **scripts/excel_generator.py** | Places *proposals for review* into the Excel template, with review questions and field inventories | Does not execute the mappings |
| **scripts/experiment_tracker.py** | Writes the experiment log automatically after each run | Does not assess mapping correctness or send data anywhere |
| **prompt.txt** | Instructions that tell Gemini how to reason from the examples | It is not program code |

## First-time setup (Windows / VS Code)

1. Open the **`ai_tool` folder** in VS Code or a PowerShell terminal.
2. Make sure Python is installed (preferably Python 3.11 or later).
3. Optional but recommended: create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. Make a local `.env` file from `.env.example`:

   ```powershell
   Copy-Item .env.example .env
   ```

6. Open `.env` and replace `replace_with_your_key` with a **valid Gemini API key**. You can also change `GEMINI_MODEL` to another model available to your account. **Never commit or share `.env`.**

## Your first mapping proposal

**Step A — Preview without consuming any Gemini quota:**

```powershell
python main.py --preview
```

This prints how many files are present, which raw examples would be sent, and an approximate prompt size. It doesn't create a workbook.

**Step B — Create a small mapping package:**

```powershell
python main.py
```

This uses the defaults: **1 historical pair per company** (3 pairs total), **2 raw new-customer XML examples**, and **10 requested target fields in one batch**.

For a more informative initial mapping of delivery items rather than the alphabetically first target fields, use:

```powershell
python main.py --target-segment E1BPOBDLVITEM --limit-targets 10
```

Look for a final line starting with `Created Excel:`. The workbook lives in a subfolder under `output/runs/`.

### Gradually give Gemini more real examples

You can change **two numbers** without editing any Python files:

| Experiment | Command | What Gemini receives |
|---|---|---|
| **Small start** | `python main.py --history-pairs 1 --source-samples 2` | 1 pair from each of the 3 companies; 2 raw new-customer XMLs |
| **A little more history** | `python main.py --history-pairs 2 --source-samples 2` | 2 pairs from each company (6 total); 2 raw new-customer XMLs |
| **More customer examples** | `python main.py --history-pairs 2 --source-samples 4` | 6 historical pairs; 4 raw new-customer XMLs, if they fit the raw-XML budget |
| **All target fields** | `python main.py --history-pairs 1 --source-samples 2 --limit-targets 0` | 3 historical pairs and 2 customer XMLs for every target batch; all target paths requested |

Add `--preview` to **any** command to check the size and selected files before using your Gemini quota. More examples increase context and token usage; **they do not guarantee better mapping quality**. Compare the Excel proposals with expert judgment.

**Other useful options:**

- `--batch-size 5` maps five target fields per API call (more calls, smaller responses).
- `--target-segment E1BPOBDLVITEM` focuses on target delivery-item fields.
- `--max-source-chars 400000` increases the combined size allowance for the *complete* raw customer XML examples. The program never sends half of a document; it selects fewer if necessary.
- `--model MODEL_NAME` temporarily chooses another available Gemini model.
- `python main.py --help` lists every option.

**Example with a bigger XML allowance:**

```powershell
python main.py --history-pairs 2 --source-samples 4 --max-source-chars 400000 --limit-targets 10 --preview
```

**How many files does Gemini actually see?** The console says `Raw customer XMLs provided to Gemini` and `Matched historical pairs provided to Gemini`. It does **not** receive all 400 historical pairs unless you explicitly choose a very large number—which may exceed your API limits.

## Output and resuming an interrupted run

Each unique set of files and settings gets its own folder, for example:

```text
output/runs/history1_source2_targets10_ab12cd34/
├── mapping_package.xlsx       The actual mapping review workbook
├── mapping_proposals.json     Gemini's structured proposals after validation
├── rejected_proposals.json    Invalid target entries, if any
├── validation_issues.json     Structural warnings, if any
├── run_info.json              Exactly what was sent and which settings were used
└── checkpoints/              Saved completed batches
```

If Gemini is overloaded (**503**) or you've reached a per-minute quota (**429**), a completed batch is kept. **Rerun the exact same command** and it will resume where it left off. Daily quotas may require waiting for a quota reset or changing your API plan. Increasing the number of examples can make a single request too large for your quota; use `--preview` before experimenting.

If `mapping_package.xlsx` is open in Excel during a rerun, close it before saving. The generator can also use a `_new.xlsx` fallback filename.

## Experiment tracking (automatic; no separate command)

Every normal `python main.py ...` execution records **one row** in `output/experiments.csv`. This file can be opened in Excel and is kept **only on your computer**, not on GitHub. The same information is also saved as an individual JSON record in the **central `output/experiments/` folder** (not inside `runs/`). Both files remain outside Git. Each record contains `run_folder` and `workbook_path` to link it to the corresponding mapping output.

**What it records automatically:**

| Column / group | Plain-English meaning |
|---|---|
| `run_id`, `started_utc`, `finished_utc`, `status` | Which execution, when it happened, and whether it completed |
| `model` | Which Gemini model you requested |
| `dataset_version` | First 12 characters of a content fingerprint across **all source and historical XML files**; changes if any XML content/file path changes |
| `prompt_sha256`, `code_version` | Fingerprints of the prompt and the project code/template, so changes can be traced |
| `history_pairs_per_company`, `historical_pairs_sent`, `source_samples_sent` | Exactly how many complete historical pairs and customer files were supplied |
| `targets_requested`, `batch_size`, `batches_total`, `batches_restored` | What was mapped and whether cached checkpoints were reused |
| `api_attempts`, `api_retries`, `api_errors` | How many Gemini API attempts, retries and errors occurred |
| `input_tokens`, `output_tokens`, `total_tokens` | Sum of **reported usage** over new Gemini responses in this execution, including any repair requests; blank if no usage was reported |
| `duration_seconds` | Runtime in seconds, including local XML processing and Excel export |
| `mapping_rows`, `placeholders`, `rejected_proposals`, `structural_issues` | Output completeness and basic structural checks, **not mapping accuracy** |
| `workbook_path` | Location of that experiment's Excel result |
| `expert_review_status` | Starts as `pending`; a human reviewer may update it after reviewing the Excel |

No raw XML, API key or full Gemini prompt is copied into the tracking CSV or JSON file. An error entry records only the error type, stage and HTTP code (if available), not the API's full error text.

### A practical experiment sequence

Run a small experiment first:

```powershell
python main.py --history-pairs 1 --source-samples 2 --target-segment E1BPOBDLVITEM --limit-targets 10
```

Then increase only the historical evidence:

```powershell
python main.py --history-pairs 2 --source-samples 2 --target-segment E1BPOBDLVITEM --limit-targets 10
```

Open `output/experiments.csv` in Excel. The two rows show the **settings**, **tokens**, **time**, **API reliability**, and **workbook locations** side by side. Open both mapping workbooks to assess **which one offers more useful mapping proposals**. A stronger experiment keeps the model, target segment and number of target fields the same while varying just one setting.

**After an Essers expert reviews the workbook:** You can manually fill the review columns in `experiments.csv` (`expert_review_status`, `expert_correct`, `expert_partial`, `expert_incorrect`, `expert_unverifiable`, `expert_acceptance_rate`). Suggested acceptance rate: `100 × correct / (correct + partial + incorrect)`; exclude unverifiable cases from the denominator, and leave the rate blank if no proposals have been reviewed. Use the same review criteria each time. The program intentionally **does not invent an accuracy percentage** from confidence scores or structural validation. Human review edits to the CSV aren't reflected in the original per-run JSON snapshot.

**Existing experiment records:** If you already ran the earlier tracking version, its JSON records will stay under `output/runs/<run-name>/experiments/`. This update puts **new** records in `output/experiments/`; it does not move or delete older files. Your existing `output/experiments.csv` remains unchanged and continues to accumulate records. To move old records into the central folder manually (optional), run from `ai_tool/` in PowerShell:

```powershell
New-Item -ItemType Directory -Force output/experiments | Out-Null
Get-ChildItem output/runs -Recurse -Filter *.json | Where-Object { $_.Directory.Name -eq "experiments" } | Move-Item -Destination output/experiments
```

This moves only experiment JSON records and leaves all run mapping packages/checkpoints alone. The old `experiments/` directories may remain empty; they can be deleted manually if desired.

**Preview and resume details:**

- `python main.py --preview` does not call Gemini and **does not add** an experiment row.
- If a batch was completed previously, running the **same command** restores its checkpoint. A new invocation row will appear with `batches_restored > 0` and possibly `api_attempts = 0`, because no new Gemini inference was performed. **Do not interpret a cached run as a new experiment.**
- If a run fails while calling Gemini, it is logged with `status=failed` and its completed batches are still safe. The next run can resume.
- Dataset and prompt hashes are content fingerprints, not a secure data-storage or dataset-approval system. Keep the XMLs in approved storage and out of Git.
- The CSV is a simple local log. Teammates running on separate computers each have their own `output/experiments.csv` unless you deliberately combine their records.

## Using the tool for another customer

1. Back up or archive the current `data/source/` XMLs somewhere outside the project.
2. Put the **new customer's ORIGINAL XML files** into `data/source/`.
3. Keep `data/historical/` unchanged; those are the previous conversions Gemini can learn from as examples.
4. Run `python main.py --preview`, then `python main.py` (or adjust the evidence counts).
5. Have an Essers integration specialist review the generated Excel before anyone implements a mapping.

To add another historical company later, create `data/historical/company_name/` and put its matching `*_Original.xml` and `*_Converted.xml` documents there. Missing or duplicate partners produce an explicit error rather than being silently ignored.

## What to check in the Excel

Open **Mapping Proposal** first. Check whether the source field actually represents the target's business meaning, and whether qualifiers, date/time conversions, quantity units, repeating item/partner loops and constants have been described correctly. The **Review Questions** sheet collects ambiguities. **Reference Evidence** lists which historic XML pairs were shown to Gemini; it does not claim those pairs are expert-verified mappings.

**No valid path error** means only that the proposed source/target paths exist. It does **not** prove a mapping is semantically correct. A higher confidence score is not a measured accuracy rate. The tool cannot invent undocumented customer-specific rules, so human review is always required.

## Privacy and teamwork

Only use XML files that Essers explicitly authorizes for an external AI API. The files included here were supplied as scrambled examples; don't substitute real customer personal or confidential data without approval. `.env` is ignored by Git. The `.gitignore` excludes the entire `data/` and `output/` folders from Git; datasets, generated workbooks and experiment logs stay local.

Your teammates need Python, the dependency installation, their own authorized API key, and access to the same scrambled example files to run this project. There is **no web frontend or deployment server** yet; this is a local command-line prototype.
