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
| **scripts/excel_generator.py** | Places approved-for-review *proposals* into the Excel template, with review questions and field inventories | Does not execute the mappings |
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

Only use XML files that Essers explicitly authorizes for an external AI API. The files included here were supplied as scrambled examples; don't substitute real customer personal or confidential data without approval. `.env` is ignored by Git. The `.gitignore` also excludes XML files by default so new datasets are not accidentally committed.

Your teammates need Python, the dependency installation, their own authorized API key, and access to the same scrambled example files to run this project. There is **no web frontend or deployment server** yet; this is a local command-line prototype.
