"""Unit tests for Mapping Converter core parsing logic."""

import io
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest

from converter import convert_excel_to_json_file, convert_excel_to_sftp, parse_mapping_excel
from models import MappingEntry, MappingPackage


def test_parse_mapping_excel_from_nouryon_proposal():
    proposal_path = Path(__file__).resolve().parents[2] / "data/shared-sftp/Proposals/nouryon/v4/MProposal-Nouryon_V4.xlsx"
    if not proposal_path.exists():
        pytest.skip(f"Sample proposal not found at {proposal_path}")

    package = parse_mapping_excel(str(proposal_path))
    assert isinstance(package, MappingPackage)
    assert len(package.mappings) == 5

    first = package.mappings[0]
    assert first.source_path == "/DELVRY03/IDOC/E1EDL20/E1EDT13/NTEND"
    assert first.target_path == "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_DATE"

    second = package.mappings[1]
    assert second.source_path == "/DELVRY03/IDOC/E1EDL20/VBELN"
    assert second.target_path == "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_NUMB"


def test_parse_mapping_excel_from_bytes():
    proposal_path = Path(__file__).resolve().parents[2] / "data/shared-sftp/Proposals/nouryon/v4/MProposal-Nouryon_V4.xlsx"
    if not proposal_path.exists():
        pytest.skip(f"Sample proposal not found at {proposal_path}")

    raw_bytes = proposal_path.read_bytes()
    package = parse_mapping_excel(raw_bytes)
    assert len(package.mappings) == 5


def test_parse_mapping_excel_with_in_memory_workbook():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mapping Proposal"

    # Category header row 1
    ws.append(["TARGET", "", "SOURCE", ""])

    # Column header row 2
    ws.append([
        "Target segment path",
        "Target field name",
        "Source full path",
        "Extra Notes",
    ])

    # Row 3: Standard mapping
    ws.append([
        "/TARGET/HDR",
        "DOC_ID",
        "/SOURCE/HEADER/ID",
        "ok",
    ])

    # Row 4: Source segment & field combination instead of full path
    ws.append([
        "/TARGET/ITEM",
        "QTY",
        "",
        "no full path",
    ])

    # Row 5: Empty row with styling/spaces only
    ws.append([None, "  ", None, None])

    # Row 6: Another valid mapping
    ws.append([
        "/TARGET/FOOTER",
        "CHECKSUM",
        "/SOURCE/FOOTER/HASH",
        "footer",
    ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    package = parse_mapping_excel(buf)
    assert len(package.mappings) == 3

    assert package.mappings[0] == MappingEntry(
        source_path="/SOURCE/HEADER/ID",
        target_path="/TARGET/HDR/DOC_ID",
    )
    assert package.mappings[1] == MappingEntry(
        source_path=None,
        target_path="/TARGET/ITEM/QTY",
    )
    assert package.mappings[2] == MappingEntry(
        source_path="/SOURCE/FOOTER/HASH",
        target_path="/TARGET/FOOTER/CHECKSUM",
    )


def test_parse_mapping_excel_direct_target_path():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Custom Mappings"

    # Headers on row 1
    ws.append(["Target full path", "Source full path"])
    ws.append(["/ROOT/TARGET_NODE", "/ROOT/SOURCE_NODE"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    package = parse_mapping_excel(buf)
    assert len(package.mappings) == 1
    assert package.mappings[0].source_path == "/ROOT/SOURCE_NODE"
    assert package.mappings[0].target_path == "/ROOT/TARGET_NODE"


def test_convert_excel_to_json_file(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mapping Proposal"

    ws.append(["Category"])
    ws.append(["Target segment path", "Target field name", "Source full path"])
    ws.append(["/ORDER/HEADER", "ORDER_NUM", "/INVOICE/INV_NUM"])

    excel_file = tmp_path / "test_proposal.xlsx"
    wb.save(excel_file)

    output_json = tmp_path / "mappingpackage.json"
    package = convert_excel_to_json_file(excel_file, output_json)

    assert output_json.exists()
    content = output_json.read_text(encoding="utf-8")
    assert "/ORDER/HEADER/ORDER_NUM" in content
    assert "/INVOICE/INV_NUM" in content
    assert len(package.mappings) == 1


def test_convert_excel_to_sftp():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mapping Proposal"
    ws.append(["Target segment path", "Target field name", "Source full path"])
    ws.append(["/ORDER/HEADER", "ORDER_NUM", "/INVOICE/INV_NUM"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    with patch("converter.save_mapping_package_to_sftp", return_value="/Packages/nouryon/v4/outbound/MPackage.json") as mock_save:
        package, sftp_path = convert_excel_to_sftp(
            excel_source=buf.getvalue(),
            company="Nouryon",
            version="v4",
            message_type="outbound",
            user_created="analist_a",
            package_version="1.0.0",
        )

    assert len(package.mappings) == 1
    assert sftp_path == "/Packages/nouryon/v4/outbound/MPackage.json"
    assert mock_save.called

