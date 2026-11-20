"""Reading the mapping rows from a proposal workbook for the AI review (scripts/excel_review.py)."""
import io
import zipfile

import pytest

from scripts.excel_review import InvalidWorkbook, read_mapping_proposal


def test_read_excel_fields(mapping_workbook):
    records = read_mapping_proposal(mapping_workbook())
    assert len(records) == 1
    assert records[0]["Source full path"] == "/Order/Id"
    assert records[0]["excel_row"] == 3


def test_case_insensitive_sheet_name(mapping_workbook):
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(mapping_workbook()), "r") as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b'name="Mapping Proposal"', b'name="mapping proposal"')
            zout.writestr(item, content)

    records = read_mapping_proposal(buf.getvalue())
    assert len(records) == 1
    assert records[0]["Source full path"] == "/Order/Id"


def test_corrupt_workbook_rejected():
    with pytest.raises(InvalidWorkbook):
        read_mapping_proposal(b"not a workbook")
