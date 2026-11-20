"""Core mapping conversion logic: parses an Excel proposal into a JSON mapping package."""

import io
from pathlib import Path
from typing import Any, BinaryIO

import openpyxl

from models import MappingEntry, MappingPackage
from sftp_service import save_mapping_package_to_sftp


def _normalize_header(value: Any) -> str:
    """Normalize header text for case- and whitespace-insensitive matching."""
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("_", "")


def _select_mapping_sheet(workbook: openpyxl.Workbook) -> Any:
    """Select the worksheet containing the mapping proposal."""
    for name in workbook.sheetnames:
        if name.strip().lower() == "mapping proposal":
            return workbook[name]

    for name in workbook.sheetnames:
        lower = name.strip().lower()
        if "mapping" in lower or "proposal" in lower:
            return workbook[name]

    sheet = workbook.active
    if sheet is None:
        raise ValueError("Workbook contains no readable worksheets")
    return sheet


def _find_header_row(sheet: Any) -> int:
    """Locate the row containing column headers."""
    header_row = 2  # standard Nouryon template row
    for r in range(1, min(6, sheet.max_row + 1)):
        row_vals = [_normalize_header(sheet.cell(r, c).value) for c in range(1, sheet.max_column + 1)]
        if any("sourcefullpath" in v or "sourcepath" in v or "targetfield" in v for v in row_vals):
            return r
    return header_row


def _find_header_row_and_sheet(workbook: openpyxl.Workbook) -> tuple[Any, int]:
    """Locate the mapping sheet and the row containing column headers."""
    sheet = _select_mapping_sheet(workbook)
    return sheet, _find_header_row(sheet)


def _get_column_indices(sheet: Any, header_row: int) -> dict[str, int]:
    """Index normalized column headers by their worksheet column."""
    return {
        _normalize_header(sheet.cell(header_row, col_idx).value): col_idx
        for col_idx in range(1, sheet.max_column + 1)
        if sheet.cell(header_row, col_idx).value is not None
    }


def _find_column(col_indices: dict[str, int], *candidates: str) -> int | None:
    """Find a column by trying multiple header names."""
    for candidate in candidates:
        column = col_indices.get(_normalize_header(candidate))
        if column is not None:
            return column
    return None


def _get_cell_text(sheet: Any, row_idx: int, col_idx: int | None) -> str | None:
    """Read a trimmed, non-empty cell value."""
    if col_idx is None:
        return None
    value = sheet.cell(row_idx, col_idx).value
    text = str(value).strip() if value is not None else ""
    return text or None


def _build_path(segment: str | None, field: str | None) -> str | None:
    """Build a path from segment and field components."""
    if segment and field:
        return f"{segment.rstrip('/')}/{field.lstrip('/')}"
    return segment or field


def _extract_path(
    sheet: Any,
    row_idx: int,
    full_column: int | None,
    segment_column: int | None,
    field_column: int | None,
) -> str | None:
    """Read a full path or construct one from segment and field columns."""
    full_path = _get_cell_text(sheet, row_idx, full_column)
    if full_path:
        return full_path
    return _build_path(
        _get_cell_text(sheet, row_idx, segment_column),
        _get_cell_text(sheet, row_idx, field_column),
    )


def _column_mapping(col_indices: dict[str, int]) -> dict[str, int | None]:
    """Resolve the supported source and target column names."""
    return {
        "source_full": _find_column(col_indices, "Source full path", "Source path", "sourcefullpath", "sourcepath"),
        "source_segment": _find_column(col_indices, "Source segment path", "sourcesegmentpath"),
        "source_field": _find_column(
            col_indices, "Source field name", "Source field", "sourcefieldname", "sourcefield"
        ),
        "target_full": _find_column(col_indices, "Target full path", "Target path", "targetfullpath", "targetpath"),
        "target_segment": _find_column(
            col_indices, "Target segment path", "Target segment", "targetsegmentpath", "targetsegment"
        ),
        "target_field": _find_column(
            col_indices, "Target field name", "Target field", "targetfieldname", "targetfield"
        ),
    }


def _read_mapping_rows(sheet: Any, header_row: int, columns: dict[str, int | None]) -> list[MappingEntry]:
    """Extract valid mapping entries from worksheet rows."""
    mappings: list[MappingEntry] = []
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        target_path = _extract_path(
            sheet, row_idx, columns["target_full"], columns["target_segment"], columns["target_field"]
        )
        source_path = _extract_path(
            sheet, row_idx, columns["source_full"], columns["source_segment"], columns["source_field"]
        )
        if target_path:
            mappings.append(MappingEntry(source_path=source_path, target_path=target_path))
    return mappings


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

        col_indices = _get_column_indices(sheet, header_row)
        columns = _column_mapping(col_indices)
        return MappingPackage(mappings=_read_mapping_rows(sheet, header_row, columns))
    finally:
        workbook.close()


def convert_excel_to_json_file(excel_path: str | Path, output_json_path: str | Path) -> MappingPackage:
    """Convert an Excel proposal file to JSON and save it to the specified destination."""
    package = parse_mapping_excel(excel_path)
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    return package


def convert_excel_to_sftp(
    excel_source: str | Path | bytes | BinaryIO,
    company: str,
    version: str | int,
    message_type: str,
    user_created: str = "analist_a",
    package_version: str | None = None,
) -> tuple[MappingPackage, str]:
    """Convert an Excel proposal and upload the resulting JSON mapping package to SFTP.

    Returns:
        tuple[MappingPackage, str]: The parsed mapping package and the remote SFTP path.
    """
    package = parse_mapping_excel(excel_source)
    sftp_path = save_mapping_package_to_sftp(
        package=package,
        company=company,
        version=version,
        message_type=message_type,
        user_created=user_created,
        package_version=package_version,
    )
    return package, sftp_path
