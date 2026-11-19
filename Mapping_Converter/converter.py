"""Core mapping conversion logic: parses an Excel proposal into a JSON mapping package."""

import io
from pathlib import Path
from typing import Any, BinaryIO

import openpyxl

from models import MappingEntry, MappingPackage


def _normalize_header(value: Any) -> str:
    """Normalize header text for case- and whitespace-insensitive matching."""
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("_", "")


def _find_header_row_and_sheet(workbook: openpyxl.Workbook) -> tuple[Any, int]:
    """Locate the mapping sheet and the row containing column headers."""
    sheet = None
    # 1. Prefer 'Mapping Proposal' (case-insensitive)
    for name in workbook.sheetnames:
        if name.strip().lower() == "mapping proposal":
            sheet = workbook[name]
            break

    # 2. Fallback to any sheet containing 'mapping' or 'proposal'
    if sheet is None:
        for name in workbook.sheetnames:
            lower = name.strip().lower()
            if "mapping" in lower or "proposal" in lower:
                sheet = workbook[name]
                break

    # 3. Fallback to active sheet
    if sheet is None:
        sheet = workbook.active

    if sheet is None:
        raise ValueError("Workbook contains no readable worksheets")

    # Locate the header row by looking for target/source columns in the first 5 rows
    header_row = 2  # standard Nouryon template row
    for r in range(1, min(6, sheet.max_row + 1)):
        row_vals = [_normalize_header(sheet.cell(r, c).value) for c in range(1, sheet.max_column + 1)]
        if any("sourcefullpath" in v or "sourcepath" in v or "targetfield" in v for v in row_vals):
            header_row = r
            break

    return sheet, header_row


def parse_mapping_excel(file_source: str | Path | bytes | BinaryIO) -> MappingPackage:
    """Read an Excel mapping proposal and extract source and target path pairs.

    Args:
        file_source: File path, raw bytes, or readable binary stream.

    Returns:
        MappingPackage containing all extracted MappingEntry items.
    """
    if isinstance(file_source, bytes):
        file_source = io.BytesIO(file_source)

    workbook = openpyxl.load_workbook(file_source, data_only=True, read_only=False)

    try:
        sheet, header_row = _find_header_row_and_sheet(workbook)

        # Index columns
        col_indices: dict[str, int] = {}
        for col_idx in range(1, sheet.max_column + 1):
            val = sheet.cell(header_row, col_idx).value
            if val is not None:
                norm = _normalize_header(val)
                col_indices[norm] = col_idx

        # Helper to find column index by multiple candidates
        def find_col(*candidates: str) -> int | None:
            for cand in candidates:
                norm_cand = _normalize_header(cand)
                if norm_cand in col_indices:
                    return col_indices[norm_cand]
            return None

        col_source_full = find_col("Source full path", "Source path", "sourcefullpath", "sourcepath")
        col_source_seg = find_col("Source segment path", "sourcesegmentpath")
        col_source_field = find_col("Source field name", "Source field", "sourcefieldname", "sourcefield")

        col_target_full = find_col("Target full path", "Target path", "targetfullpath", "targetpath")
        col_target_seg = find_col("Target segment path", "Target segment", "targetsegmentpath", "targetsegment")
        col_target_field = find_col("Target field name", "Target field", "targetfieldname", "targetfield")

        mappings: list[MappingEntry] = []

        for row_idx in range(header_row + 1, sheet.max_row + 1):
            # Extract target path
            target_path = None
            if col_target_full:
                val = sheet.cell(row_idx, col_target_full).value
                if val is not None and str(val).strip():
                    target_path = str(val).strip()

            if not target_path:
                seg_val = sheet.cell(row_idx, col_target_seg).value if col_target_seg else None
                field_val = sheet.cell(row_idx, col_target_field).value if col_target_field else None

                seg_str = str(seg_val).strip() if seg_val is not None and str(seg_val).strip() else None
                field_str = str(field_val).strip() if field_val is not None and str(field_val).strip() else None

                if seg_str and field_str:
                    target_path = f"{seg_str.rstrip('/')}/{field_str.lstrip('/')}"
                elif seg_str:
                    target_path = seg_str
                elif field_str:
                    target_path = field_str

            # Extract source path
            source_path = None
            if col_source_full:
                val = sheet.cell(row_idx, col_source_full).value
                if val is not None and str(val).strip():
                    source_path = str(val).strip()

            if not source_path:
                seg_val = sheet.cell(row_idx, col_source_seg).value if col_source_seg else None
                field_val = sheet.cell(row_idx, col_source_field).value if col_source_field else None

                seg_str = str(seg_val).strip() if seg_val is not None and str(seg_val).strip() else None
                field_str = str(field_val).strip() if field_val is not None and str(field_val).strip() else None

                if seg_str and field_str:
                    source_path = f"{seg_str.rstrip('/')}/{field_str.lstrip('/')}"
                elif seg_str:
                    source_path = seg_str
                elif field_str:
                    source_path = field_str

            # Ignore pre-styled blank rows
            if not target_path and not source_path:
                continue

            # Target path is mandatory for a valid mapping rule
            if target_path:
                mappings.append(MappingEntry(source_path=source_path, target_path=target_path))

        return MappingPackage(mappings=mappings)
    finally:
        workbook.close()


def convert_excel_to_json_file(excel_path: str | Path, output_json_path: str | Path) -> MappingPackage:
    """Convert an Excel proposal file to JSON and save it to the specified destination."""
    package = parse_mapping_excel(excel_path)
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    return package
