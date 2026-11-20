"""Export into the provided Nouryon Excel layout, keeping existing formatting.

This uses openpyxl in the user's Python environment. The layout is read from
row 2 of 'Mapping Proposal', and row 1 of the other worksheets.
"""

import logging
from copy import copy
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# Excel allows 32,767 characters per cell; keep a safety margin.
MAX_CELL_CHARS = 32000
MAPPING_SHEET = 'Mapping Proposal'
RULE_TYPES_SHEET = 'Rule Types'


def _text(value):
    """Convert to a string that fits in one Excel cell."""
    if value is None:
        return None
    return str(value)[:MAX_CELL_CHARS]


def _headers(sheet, row):
    """Header names of one row, up to the last non-empty header cell."""
    values = [cell.value for cell in sheet[row]]
    while values and values[-1] in (None, ''):
        values.pop()
    return values


def _clear_old_rows(sheet, start_row):
    for row in sheet.iter_rows(min_row=start_row):
        for cell in row:
            cell.value = None


def _copy_template_style(sheet, template_row, row_number, col_index, cell):
    """Apply the first data row's formatting to subsequent records."""
    if row_number == template_row:
        return
    model_cell = sheet.cell(template_row, col_index)
    if model_cell.has_style:
        cell._style = copy(model_cell._style)
    cell.alignment = copy(model_cell.alignment)


def _write_cell_value(cell, value):
    """Preserve numeric values and prevent user text from becoming formulas."""
    if isinstance(value, (int, float, bool)):
        cell.value = value
        return
    cell.value = _text(value)
    if cell.value is not None:
        cell.data_type = 's'


def _write_records(sheet, headers, records, start_row):
    for index, record in enumerate(records):
        row_number = start_row + index
        for col_index, header in enumerate(headers, start=1):
            cell = sheet.cell(row_number, col_index)
            _copy_template_style(sheet, start_row, row_number, col_index, cell)
            _write_cell_value(cell, record.get(header))


def _write_sheet_records(workbook, sheet_name, header_row, records, start_row):
    sheet = workbook[sheet_name]
    _write_records(sheet, _headers(sheet, header_row), records, start_row)


def _mapping_reason(mapping):
    summary = str(mapping.get('reason', ''))
    problems = mapping.get('validation_issues', [])
    if problems:
        summary += ' | VALIDATION: ' + '; '.join(problems)
    return summary


def _mapping_record(mapping, mapping_id, source_detail, summary):
    target = mapping['target_path']
    source = mapping['source_path']
    return {
        'Mapping ID': mapping_id,
        'Runtime source group': 'New customer original XML',
        'Runtime source file example': (source_detail.get('files') or [''])[0],
        'Confidence %': mapping['confidence'],
        'Requires review': 'Yes' if mapping['requires_review'] else 'No',
        'Review priority': mapping.get('review_priority', ''),
        'Confidence reason': summary,
        'Evidence summary': mapping.get('evidence', ''),
        'Target segment path': target.rsplit('/', 1)[0],
        'Target segment name': target.rsplit('/', 2)[-2] if '/' in target else '',
        'Target field name': target.rsplit('/', 1)[-1],
        'Target field description': '',
        'Source segment path': source.rsplit('/', 1)[0] if source else '',
        'Source field name': source.rsplit('/', 1)[-1] if source else '',
        'Source full path': source,
        'Example source value': ' | '.join(source_detail.get('examples', [])[:3]),
        'Proposed rule type': mapping['rule_type'],
        'Fixed value': mapping.get('fixed_value', ''),
        'Transformation logic': mapping.get('transformation', ''),
        'Condition logic': mapping.get('condition', ''),
        'Lookup logic': mapping.get('lookup', ''),
        'Loop mapping logic': mapping.get('loop', ''),
        'Risk category': mapping.get('risk_category', ''),
    }


def _review_question(mapping, mapping_id, source_detail, summary, question_number):
    return {
        'Question ID': f'RQ-{question_number:03d}',
        'Question priority': mapping.get('review_priority') or 'Medium',
        'Question type': 'Mapping review',
        'Related Mapping ID(s)': mapping_id,
        'Runtime source file(s)': ', '.join(source_detail.get('files', [])),
        'Target field(s)': mapping['target_path'],
        'Source candidate(s)': mapping['source_path'],
        'Question': mapping.get('review_question') or 'Confirm the proposed mapping.',
        'Why this question matters': summary,
        'Impacted mappings count': 1,
        'Suggested answer': '',
        'Impact if unanswered': mapping.get('risk_category', ''),
        'Status': 'Open',
    }


def _mapping_and_question_records(mappings, source_inventory):
    records, questions = [], []
    for index, mapping in enumerate(mappings, 1):
        mapping_id = f'MP-{index:03d}'
        source_detail = next(
            (field for field in source_inventory if field['path'] == mapping['source_path']),
            {},
        )
        summary = _mapping_reason(mapping)
        records.append(_mapping_record(mapping, mapping_id, source_detail, summary))
        if mapping['requires_review']:
            questions.append(
                _review_question(mapping, mapping_id, source_detail, summary, len(questions) + 1)
            )
    return records, questions


def _inventory_records(source_inventory):
    return [{
        'Source full path': field['path'],
        'Source field name': field['field'],
        'Runtime files count': len(field['files']),
        'Occurrences': field['count'],
        'Runtime files': ', '.join(field['files']),
        'Example values': ' | '.join(field['examples']),
    } for field in source_inventory]


def _classification_record(file, classification, role, group, comment):
    """Use consistent column keys for each file-classification row."""
    return {
        'File': file.name,
        'Classification': classification,
        'Role in execution': role,
        'Pair/group': group,
        'Comment': comment,
    }


def _historical_classification_records(pair):
    group = f"{pair['company']} / {pair['pair_id']}"
    return [
        _classification_record(
            pair['original_file'], 'Historical Original',
            'Historical conversion evidence', group,
            'Matched to converted file; may be sampled for AI context',
        ),
        _classification_record(
            pair['converted_file'], 'Historical Converted',
            'Common target inventory and historical evidence', group,
            'Historical target structure; paired with original',
        ),
    ]


def _file_classification_records(source_files, target_files, historical_pairs):
    records = [
        _classification_record(
            file, 'Runtime Original', 'New customer source inventory',
            'Current customer', 'Unconverted customer input',
        )
        for file in source_files
    ]
    for pair in historical_pairs:
        records.extend(_historical_classification_records(pair))
    if not historical_pairs:
        records.extend(
            _classification_record(
                file, 'Target Example', 'Target inventory', 'Current', 'Target example',
            )
            for file in target_files
        )
    return records


def _write_summary(workbook, mappings, source_inventory, source_files, target_files,
                   historical_pairs, selected_historical_examples, question_count):
    summary = workbook['Summary']
    supplied_count = len(source_files) + (
        2 * len(historical_pairs) if historical_pairs else len(target_files)
    )
    summary_items = [
        ('Aantal aangeleverde bestanden', supplied_count),
        ('Aantal Runtime Original-bestanden', len(source_files)),
        ('Gekozen werkingsmodus', 'AI Mapping Prototype (human review)'),
        ('Aantal voorgestelde mappings', len(mappings)),
        ('Aantal high confidence mappings', sum(m['confidence'] >= 90 for m in mappings)),
        ('Aantal mappings requiring review', question_count),
        ('Aantal source paths discovered', len(source_inventory)),
        ('Historical pairs discovered', len(historical_pairs)),
        ('Historical pairs sent to Gemini per batch', len(selected_historical_examples)),
    ]
    for index, (label, value) in enumerate(summary_items, 2):
        summary.cell(index, 1).value = label
        summary.cell(index, 2).value = value


def _reference_records(verified_historical_evidence, selected_historical_examples):
    """Include selected pairs without exact-value matches as context-only evidence."""
    records = list(verified_historical_evidence)
    with_matches = {row['Reference pair'] for row in records}
    for pair in selected_historical_examples:
        pair_label = f"{pair['company']} / {pair['pair_id']}"
        if pair_label in with_matches:
            continue
        records.append({
            'Reference pair': pair_label,
            'Historical Original': pair['original_filename'],
            'Historical Converted': pair['converted_filename'],
            'Evidence type': 'Context only (no informative exact match)',
            'Historical source path': '',
            'Historical target path': '',
            'Example value': '',
            'Evidence note': 'Pair was supplied to Gemini; no informative field-level exact match was found.',
            'Usefulness': 'Context only',
        })
    return records


def _restore_rule_types(workbook, template_path):
    """Restore the template's rule codebook after clearing old data rows."""
    rules = workbook[RULE_TYPES_SHEET]
    original = load_workbook(template_path, read_only=True)
    try:
        original_rules = original[RULE_TYPES_SHEET]
        for row in original_rules.iter_rows(min_row=2):
            for cell in row:
                rules.cell(cell.row, cell.column).value = cell.value
    finally:
        original.close()


def _save_workbook(workbook, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        workbook.save(output_path)
    except PermissionError:
        backup_path = output_path.with_name(output_path.stem + '_new.xlsx')
        workbook.save(backup_path)
        logger.warning('Original Excel file is locked. Saved to: %s', backup_path)
        return backup_path
    return output_path


def export_excel(mappings, source_inventory, source_files, target_files,
                 output_path: str | Path, template_path: str | Path,
                 historical_pairs=None, selected_historical_examples=None,
                 verified_historical_evidence=None):
    """Populate the mapping template without altering its sheet structure."""
    historical_pairs = historical_pairs or []
    selected_historical_examples = selected_historical_examples or []
    verified_historical_evidence = verified_historical_evidence or []
    template_path, output_path = Path(template_path), Path(output_path)
    if not template_path.exists():
        raise FileNotFoundError(f'Excel template not found: {template_path}')
    workbook = load_workbook(template_path)

    for sheet in workbook:
        _clear_old_rows(sheet, 3 if sheet.title == MAPPING_SHEET else 2)

    mapping_records, questions = _mapping_and_question_records(mappings, source_inventory)
    _write_sheet_records(workbook, MAPPING_SHEET, 2, mapping_records, 3)
    _write_sheet_records(workbook, 'Review Questions', 1, questions, 2)
    _write_sheet_records(workbook, 'Runtime Field Inventory', 1,
                         _inventory_records(source_inventory), 2)
    _write_sheet_records(workbook, 'File Classification', 1,
                         _file_classification_records(source_files, target_files, historical_pairs), 2)
    _write_summary(workbook, mappings, source_inventory, source_files, target_files,
                   historical_pairs, selected_historical_examples, len(questions))
    _write_sheet_records(workbook, 'Reference Evidence', 1,
                         _reference_records(verified_historical_evidence,
                                            selected_historical_examples), 2)
    _restore_rule_types(workbook, template_path)
    return _save_workbook(workbook, output_path)
