"""Shared pytest fixtures for the Mapping Converter tests.

Tests never use the real SFTP server: they use a temporary folder (LocalStorage),
and never call Gemini: the AI review is replaced by a fake in every test that needs it.
"""
import html
import io
import zipfile

import pytest

from services.storage import LocalStorage


@pytest.fixture
def proposals_root(tmp_path):
    root = tmp_path / 'proposals'
    root.mkdir()
    return root


@pytest.fixture
def proposals_storage(proposals_root):
    return LocalStorage(proposals_root)


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def example_xlsx(*, rule="DIRECT", source="/Order/Id", fixed=""):
    headers = ["Mapping ID", "Target field name", "Source full path", "Proposed rule type", "Fixed value"]
    values = ["MP-001", "ID", source, rule, fixed]

    def row(number, cells):
        parts = []
        for column, value in enumerate(cells):
            if value:
                letter = chr(ord("A") + column)
                parts.append(f'<c r="{letter}{number}" t="inlineStr"><is><t>{html.escape(value)}</t></is></c>')
        return f'<row r="{number}">{"".join(parts)}</row>'

    sheet = f'<worksheet xmlns="{MAIN_NS}"><sheetData>' + row(2, headers) + row(3, values) + "</sheetData></worksheet>"
    workbook = (
        f'<workbook xmlns="{MAIN_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Mapping Proposal" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zipf:
        zipf.writestr("xl/workbook.xml", workbook)
        zipf.writestr("xl/_rels/workbook.xml.rels", rels)
        zipf.writestr("xl/worksheets/sheet1.xml", sheet)
    return out.getvalue()


@pytest.fixture
def mapping_workbook():
    """Factory for a minimal valid "Mapping Proposal" workbook (as bytes)."""
    return example_xlsx
