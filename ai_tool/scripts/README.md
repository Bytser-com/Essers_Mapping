# How the Essers AI Mapping Scripts Work

This README explains the Python scripts in our **H. Essers XML mapping prototype**, step by step. It is intended for teammates who want to understand what the code does without needing to know every implementation detail.

**The goal:** Use previous *original → converted* XML examples to help Gemini suggest how a new customer's XML fields should map to the target XML format. The suggestions are exported to Excel for **human review**.

> **Important:** Python organizes files and checks structure. **Gemini proposes the mapping logic.** Neither a structurally valid proposal nor a high Gemini confidence score proves that the mapping satisfies Essers' business rules.

## 1. The overall workflow

```text
data/source/                       data/historical/
New customer XMLs                   Original + Converted XML pairs
          \                           /
           \                         /
            scripts/xml_parser.py
              |  - scans XML fields
              |  - selects representative raw examples
              v
            scripts/readprompt.py <---- prompt.txt + RULE_SCHEMA
              |  - sends raw XML examples and field indexes to Gemini
              |  - receives JSON mapping proposals
              v
            scripts/mapping_validator.py
              |  - checks paths, rules, required values, etc.
              v
            scripts/excel_generator.py <---- templates/mapping_template.xlsx
              |  - fills the Excel template
              v
            output/runs/<run-name>/mapping_package.xlsx

            scripts/experiment_tracker.py
              -> output/experiments.csv
              -> output/experiments/<run-id>.json
```

`main.py` coordinates these scripts: it calls them in the correct order, handles batches and checkpoints, and saves the results.

## 2. `xml_parser.py` — Read XML files and choose examples

### A. Discover fields in all files

Python scans **all new-customer XML files** to build a list of existing *source paths*. It also scans **all historical converted XML files** to discover existing *target paths*.

A *path* means the location of a particular field in an XML document. For example:

```xml
<Shipment>
    <OrderReference>12345</OrderReference>
</Shipment>
```

The path of `OrderReference` is `/Shipment/OrderReference`.

The field inventory includes each discovered leaf-element or attribute path, the number of times it occurs, which files contain it, and up to three example values. **Occurrence count means appearances, not necessarily the number of distinct files** (because an XML can repeat an item).

A simplified excerpt of the real code:

```python
def record(path, kind, value):
    item = found[(path, kind)]
    item['count'] += 1
    item['files'].add(file.name)
    if value and value not in item['examples'] and len(item['examples']) < 3:
        item['examples'].append(value[:100])
```

### B. Select representative new-customer XMLs

We don't send every complete XML document to Gemini by default. Python compares their *structure* and prioritizes documents that add new paths or different repetition patterns.

This is the key part of the selection code:

```python
new_paths = len(structural - covered)
score = (new_paths, len(structural), -len(content), file.name)
```

Here:

- `structural` = the paths and repetition patterns in the candidate file.
- `covered` = the structural patterns already represented by selected files.
- `structural - covered` = the patterns this file would add.

For example, if file A contains fields `A, B, C` and file B adds only `D`, another file containing `E, F` may be a better second choice. The algorithm tries to **cover varied structures**, not simply select the largest files. It also respects a character budget for the new-customer examples and does not truncate selected XMLs.

### C. Select historical original/converted pairs

For each historical company (Christeyns, Chugoku, Hempel), Python compares the **original** files in that company's dataset, selects structurally varied originals, and includes each selected original's **matching converted XML**.

```python
pair = pair_by_file[doc['path']]
selected.append({
    'original_xml': doc['xml'],
    'converted_xml': read_raw_xml(pair['converted_file']),
    # ... company and filename details
})
```

It does **not** attempt to discover the mappings between those files. That is Gemini's task.

**Crucial distinction:** Selected documents are sent as **complete raw XML text**. The field inventories are additionally sent as compact JSON indexes. Python does not transform the selected XML into JSON or summarize its business meaning.

## 3. `readprompt.py` — Ask Gemini for mapping proposals

This script prepares the API request from:

1. Instructions stored in `prompt.txt`.
2. The source/target field inventories assembled by Python.
3. Selected **raw** XMLs from the new customer.
4. Selected historical **original + converted** raw XML pairs.
5. A required JSON response structure (`RULE_SCHEMA`).

The instructions are loaded from the prompt file:

```python
instructions = (ROOT / 'prompt.txt').read_text(encoding='utf-8')
```

`prompt.txt` tells Gemini **what to do** (analyze historical conversions, propose mappings, explain uncertainty). `RULE_SCHEMA` tells Gemini **how to format its answer**. The schema is passed separately in the API configuration:

```python
config=types.GenerateContentConfig(
    response_mime_type='application/json',
    response_json_schema=RULE_SCHEMA,
    temperature=0.1,
)
```

For example, one proposal might contain these fields (this is only a shortened illustration; the actual schema requires more):

```json
{
  "source_path": "/Shipment/OrderReference",
  "target_path": "/Delivery/DELIV_NUMB",
  "rule_type": "DIRECT",
  "confidence": 85,
  "reason": "Both appear to refer to a delivery identifier."
}
```

The source and target field names **do not have to match**. Gemini is responsible for suggesting their meaning and relationship.

### What does “processes Gemini's response” mean?

Gemini returns JSON text. Python parses it into a **list of dictionaries** that other scripts can use:

```python
result = json.loads(response.text)
if not isinstance(result, dict) or not isinstance(result.get('mappings'), list):
    raise ValueError('Gemini response did not contain a mappings list')
return result['mappings']
```

This is just a **basic response-format check**: valid JSON with a `mappings` list. It does not verify mapping correctness. The script also reports token use and retries certain temporary Gemini API errors.

## 4. `mapping_validator.py` — Check the proposals structurally

After Gemini replies, the validator checks whether the proposed mappings are *structurally plausible*.

For instance, if Gemini proposes:

```text
Source: /Shipment/OrderReference
Target: /Delivery/DELIV_NUMB
```

Python checks whether the source path occurs in the new-customer field inventory and the target path occurs in the discovered target inventory. The names **do not** have to be similar.

A small excerpt of the actual code:

```python
source_paths = {item['path'] for item in source_fields}
target_paths = {item['path'] for item in target_fields}

if target_path not in target_paths:
    rejected.append({'reason': 'Unknown target path', 'proposal': original})
    continue
if source_path and source_path not in source_paths:
    problem.append(f'Source path not found: {source_path}')
```

The validator also checks:

- Whether the rule type is supported (`DIRECT`, `FIXED`, `LOOKUP`, etc.).
- Whether a mapping needing a source path actually has one.
- Whether a `FIXED` mapping includes its fixed value.
- Whether the confidence value is a number between 0 and 100.
- Whether multiple proposals target the same field (flagged for review).

An **unknown target path is rejected**. Other structural problems generally cause the mapping to be **flagged for expert review**. `main.py` can also ask Gemini to repair omitted or invalid target proposals once.

> The validator checks whether Gemini is referring to **real fields and usable rule structures**. It does **not** establish that the source field is the correct one according to Essers' business rules.

## 5. `excel_generator.py` — Fill the mapping Excel template

The validated Python dictionaries are passed to `excel_generator.py`, which opens:

```text
templates/mapping_template.xlsx
```

The generator knows how to translate mapping information into the worksheet's **named columns**. It creates a dictionary with keys matching the Excel headers; then it reads the headers from the template and writes each corresponding value.

A shortened example based on the actual code:

```python
records.append({
    'Source full path': source,
    'Target field name': target.rsplit('/', 1)[-1],
    'Proposed rule type': m['rule_type'],
    'Confidence %': m['confidence'],
    'Transformation logic': m.get('transformation', ''),
})

headers = [main.cell(2, col).value for col in range(1, 31)]
_write_records(main, headers, records, 3)
```

So the template and generator are connected through **specific header names and worksheet layouts**. The columns are not filled by Gemini itself. If we substantially change the Excel template's headers or layout, we may also need to update the generator.

The workbook contains mapping proposals and supporting worksheets, including **Review Questions**, **Runtime Field Inventory**, **File Classification**, and **Reference Evidence**. Some Excel cells are intentionally blank when a mapping needs no transformation, condition or lookup—or when Gemini lacks sufficient evidence.

The resulting workbook is saved at:

```text
output/runs/<run-name>/mapping_package.xlsx
```

## 6. `experiment_tracker.py` — Record each execution

This script makes experiments traceable **without adding a full MLOps framework**. When `main.py` performs a run, the tracker records details such as:

- Which Gemini model, dataset fingerprint and prompt version were used.
- How many historical pairs and new-customer examples were supplied.
- Number of requested target fields and API attempts/retries.
- Input/output tokens, total duration and any errors.
- Number of proposals, structural issues, rejected proposals and placeholders.
- Which output folder contains the Excel file.

For example, `readprompt.py` reports token usage to the tracker:

```python
on_event({
    'type': 'usage',
    'input_tokens': usage.prompt_token_count,
    'output_tokens': usage.candidates_token_count,
    'total_tokens': usage.total_token_count,
})
```

The tracker writes **one record per execution**, not one separate experiment per API retry. Retries and API attempts are counted *within* the record. Results are saved centrally:

```text
output/experiments.csv                 # Overview: open in Excel
output/experiments/<run-id>.json       # Detailed record of one execution
```

The central log records technical measurements automatically. **Expert mapping correctness is not measured automatically.** A reviewer must assess the workbook before filling the expert-review fields.

## 7. `main.py` — The coordinator

You normally run **`main.py`**, not the scripts individually. It coordinates selection, Gemini requests, checkpoints, validation, Excel generation and experiment tracking.

From the `ai_tool/` folder:

```powershell
# Preview selected examples without contacting Gemini
python main.py --preview

# Default run: 1 historical pair per company, 2 source examples,
# first 10 target fields
python main.py

# Increase the context step by step
python main.py --history-pairs 2 --source-samples 3

# Map all discovered target fields (rather than just the first 10)
python main.py --history-pairs 2 --source-samples 3 --limit-targets 0
```

`--history-pairs 2` means **two original/converted pairs per historical company**, not two historical pairs total. More examples consume more tokens; keep an eye on model limits and costs.

`main.py` can also split target fields into batches and save completed batch responses as **checkpoints**. If an API request fails, rerunning the same command can reuse completed batches. The experiment log records this reuse.

## 8. What Python does *not* verify

A mapping can pass all technical checks and still be **wrong for the business**. For example, Nouryon might have several shipment identifiers and Essers might require a specific one under a particular condition. Python can confirm a path exists, but it cannot infer that internal business rule.

That is why **the Excel output is a proposal, not an approved integration**. An Essers expert must review the mapping logic, especially conditions, lookups, transformations, repeating structures and unsupported assumptions.

**In one sentence:** `xml_parser.py` chooses useful raw examples → `readprompt.py` asks Gemini for JSON mappings → `mapping_validator.py` checks their structure → `excel_generator.py` fills the template, while `experiment_tracker.py` records the execution and `main.py` coordinates everything.
