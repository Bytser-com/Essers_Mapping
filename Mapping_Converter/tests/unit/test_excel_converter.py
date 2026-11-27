"""Unit tests for services/excel_converter.py: Excel proposal -> mapping package."""
import io
from pathlib import Path

import openpyxl
import pytest

from scripts.models import MappingEntry, MappingPackage
from services.excel_converter import convert_excel_to_json_file, parse_mapping_excel

# Optional real example; the tests that need it are skipped when it is not there.
SAMPLE_PROPOSAL = Path(__file__).resolve().parents[3] / 'data/shared-sftp/Proposals/nouryon/v4/MProposal-Nouryon_V4.xlsx'


def workbook_bytes(rows, title='Mapping Proposal'):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_mapping_excel_from_nouryon_proposal():
    if not SAMPLE_PROPOSAL.exists():
        pytest.skip(f'Sample proposal not found at {SAMPLE_PROPOSAL}')

    package = parse_mapping_excel(str(SAMPLE_PROPOSAL))

    assert isinstance(package, MappingPackage)
    assert len(package.mappings) == 5
    assert package.mappings[0].source_path == '/DELVRY03/IDOC/E1EDL20/E1EDT13/NTEND'
    assert package.mappings[0].target_path == '/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_DATE'


def test_parse_mapping_excel_from_bytes_of_nouryon_proposal():
    if not SAMPLE_PROPOSAL.exists():
        pytest.skip(f'Sample proposal not found at {SAMPLE_PROPOSAL}')

    assert len(parse_mapping_excel(SAMPLE_PROPOSAL.read_bytes()).mappings) == 5


def test_parse_mapping_excel_with_standard_template_layout():
    content = workbook_bytes([
        ['TARGET', '', 'SOURCE', ''],                                           # category row 1
        ['Target segment path', 'Target field name', 'Source full path', 'Extra Notes'],  # headers row 2
        ['/TARGET/HDR', 'DOC_ID', '/SOURCE/HEADER/ID', 'ok'],
        ['/TARGET/ITEM', 'QTY', '', 'no full path'],
        [None, '  ', None, None],                                                # empty row
        ['/TARGET/FOOTER', 'CHECKSUM', '/SOURCE/FOOTER/HASH', 'footer'],
    ])

    package = parse_mapping_excel(content)

    assert package.mappings == [
        MappingEntry(source_path='/SOURCE/HEADER/ID', target_path='/TARGET/HDR/DOC_ID'),
        MappingEntry(source_path=None, target_path='/TARGET/ITEM/QTY'),
        MappingEntry(source_path='/SOURCE/FOOTER/HASH', target_path='/TARGET/FOOTER/CHECKSUM'),
    ]


def test_parse_mapping_excel_with_full_paths_on_another_sheet_name():
    content = workbook_bytes([
        ['Target full path', 'Source full path'],
        ['/ROOT/TARGET_NODE', '/ROOT/SOURCE_NODE'],
    ], title='Custom Mappings')

    package = parse_mapping_excel(io.BytesIO(content))

    assert package.mappings == [MappingEntry(source_path='/ROOT/SOURCE_NODE', target_path='/ROOT/TARGET_NODE')]


def test_source_path_is_built_from_segment_and_field():
    content = workbook_bytes([
        ['TARGET', 'SOURCE', ''],                                              # category row 1
        ['Target full path', 'Source segment path', 'Source field name'],     # headers row 2
        ['/T/A', '/S/HDR/', '/NUM'],
    ])

    assert parse_mapping_excel(content).mappings[0].source_path == '/S/HDR/NUM'


def test_convert_excel_to_json_file(tmp_path):
    excel_file = tmp_path / 'proposal.xlsx'
    excel_file.write_bytes(workbook_bytes([
        ['Category'],
        ['Target segment path', 'Target field name', 'Source full path'],
        ['/ORDER/HEADER', 'ORDER_NUM', '/INVOICE/INV_NUM'],
    ]))
    output_json = tmp_path / 'out' / 'mappingpackage.json'

    package = convert_excel_to_json_file(excel_file, output_json)

    content = output_json.read_text(encoding='utf-8')
    assert '/ORDER/HEADER/ORDER_NUM' in content
    assert '/INVOICE/INV_NUM' in content
    assert len(package.mappings) == 1


def test_unreadable_workbook_raises():
    with pytest.raises(Exception):  # noqa: B017 - openpyxl raises different error types
        parse_mapping_excel(b'not a zip or excel')
