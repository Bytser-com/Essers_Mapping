"""Parsing an Excel mapping proposal into a JSON mapping package (story 54).

The Excel layout is the template Mapping_Proposal writes ('Mapping Proposal' sheet, headers
on row 2). Other layouts work as long as the headers name the source and target paths.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO

import openpyxl

from scripts.models import MappingEntry, MappingPackage


def parse_mapping_excel(file_source: str | Path | bytes | BinaryIO) -> MappingPackage:
    """Read an Excel mapping proposal and extract the source and target path pairs.

    Args:
        file_source: File path, raw bytes, or readable binary stream.

    Returns:
        MappingPackage containing all extracted MappingEntry items (without metadata).
    """
    if isinstance(file_source, bytes):
        file_source = io.BytesIO(file_source)

    workbook = openpyxl.load_workbook(file_source, data_only=True, read_only=False)
    try:
        sheet = _select_mapping_sheet(workbook)
        header_row = _find_header_row(sheet)
        columns = _column_mapping(_get_column_indices(sheet, header_row))
        return MappingPackage(mappings=_read_mapping_rows(sheet, header_row, columns))
    finally:
        workbook.close()


def convert_excel_to_json_file(excel_path: str | Path, output_json_path: str | Path) -> MappingPackage:
    """Convert an Excel proposal file to JSON and save it locally (handy for manual checks)."""
    package = parse_mapping_excel(excel_path)
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(package.model_dump_json(indent=2), encoding='utf-8')
    return package


def _normalize_header(value: Any) -> str:
    """Normalize header text for case- and whitespace-insensitive matching."""
    if value is None:
        return ''
    return str(value).strip().lower().replace(' ', '').replace('_', '')


def _select_mapping_sheet(workbook: openpyxl.Workbook) -> Any:
    """Select the worksheet containing the mapping proposal."""
    for name in workbook.sheetnames:
        if name.strip().lower() == 'mapping proposal':
            return workbook[name]

    for name in workbook.sheetnames:
        lower = name.strip().lower()
        if 'mapping' in lower or 'proposal' in lower:
            return workbook[name]

    sheet = workbook.active
    if sheet is None:
        raise ValueError('Workbook contains no readable worksheets')
    return sheet


def _find_header_row(sheet: Any) -> int:
    """Locate the row containing the column headers (row 2 in the standard template)."""
    for row in range(1, min(6, sheet.max_row + 1)):
        values = [_normalize_header(sheet.cell(row, col).value) for col in range(1, sheet.max_column + 1)]
        if any('sourcefullpath' in v or 'sourcepath' in v or 'targetfield' in v for v in values):
            return row
    return 2


def _get_column_indices(sheet: Any, header_row: int) -> dict[str, int]:
    """Index normalized column headers by their worksheet column."""
    return {
        _normalize_header(sheet.cell(header_row, col).value): col
        for col in range(1, sheet.max_column + 1)
        if sheet.cell(header_row, col).value is not None
    }


def _find_column(col_indices: dict[str, int], *candidates: str) -> int | None:
    """Find a column by trying multiple header names."""
    for candidate in candidates:
        column = col_indices.get(_normalize_header(candidate))
        if column is not None:
            return column
    return None


def _column_mapping(col_indices: dict[str, int]) -> dict[str, int | None]:
    """Resolve the supported source and target column names."""
    return {
        'source_full': _find_column(col_indices, 'Source full path', 'Source path'),
        'source_segment': _find_column(col_indices, 'Source segment path'),
        'source_field': _find_column(col_indices, 'Source field name', 'Source field'),
        'target_full': _find_column(col_indices, 'Target full path', 'Target path'),
        'target_segment': _find_column(col_indices, 'Target segment path', 'Target segment'),
        'target_field': _find_column(col_indices, 'Target field name', 'Target field'),
    }


def _get_cell_text(sheet: Any, row: int, col: int | None) -> str | None:
    """Read a trimmed, non-empty cell value."""
    if col is None:
        return None
    value = sheet.cell(row, col).value
    text = str(value).strip() if value is not None else ''
    return text or None


def _build_path(segment: str | None, field: str | None) -> str | None:
    """Build a path from segment and field components."""
    if segment and field:
        return f"{segment.rstrip('/')}/{field.lstrip('/')}"
    return segment or field


def _extract_path(sheet: Any, row: int, full_col: int | None, segment_col: int | None,
                  field_col: int | None) -> str | None:
    """Read a full path or construct one from the segment and field columns."""
    full_path = _get_cell_text(sheet, row, full_col)
    if full_path:
        return full_path
    return _build_path(_get_cell_text(sheet, row, segment_col), _get_cell_text(sheet, row, field_col))


def _read_mapping_rows(sheet: Any, header_row: int, columns: dict[str, int | None]) -> list[MappingEntry]:
    """Extract the mapping entries; rows without a target path are skipped."""
    mappings: list[MappingEntry] = []
    for row in range(header_row + 1, sheet.max_row + 1):
        target_path = _extract_path(sheet, row, columns['target_full'], columns['target_segment'],
                                    columns['target_field'])
        source_path = _extract_path(sheet, row, columns['source_full'], columns['source_segment'],
                                    columns['source_field'])
        if target_path:
            mappings.append(MappingEntry(source_path=source_path, target_path=target_path))
    return mappings
