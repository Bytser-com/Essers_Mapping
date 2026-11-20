"""Read the Mapping Proposal worksheet from an uploaded XLSX, without executing formulas.

This intentionally reads only the uploaded workbook. It does not load historical
XML, templates, source files, SFTP contents, or any existing mapping package.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_MAPPING_ROWS = 300
MAX_CELL_LENGTH = 800

# These names match the existing Mapping Proposal worksheet's row 2.
FIELDS = (
    'Mapping ID', 'Target segment path', 'Target field name',
    'Source full path', 'Proposed rule type', 'Fixed value',
    'Transformation logic', 'Condition logic', 'Lookup logic',
    'Loop mapping logic', 'Requires review', 'Reviewer decision',
    'Reviewer corrected source path', 'Reviewer corrected rule type',
    'Reviewer corrected fixed value', 'Reviewer corrected transformation logic',
    'Reviewer corrected condition logic',
)
REQUIRED_HEADERS = {'Mapping ID', 'Target field name', 'Proposed rule type', 'Source full path'}


class InvalidWorkbook(ValueError):
    """The upload cannot be read as a supported mapping proposal."""


def _column_number(reference: str) -> int:
    letters = re.match(r'[A-Z]+', reference.upper())
    if not letters:
        raise InvalidWorkbook('Invalid Excel cell reference.')
    number = 0
    for letter in letters.group():
        number = number * 26 + ord(letter) - ord('A') + 1
    return number


def _text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get('t', '')
    if kind == 'inlineStr':
        inline = cell.find('m:is', NS)
        return ''.join(inline.itertext()) if inline is not None else ''
    value = cell.find('m:v', NS)
    if value is None or value.text is None:
        return ''
    if kind == 's':
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError) as error:
            raise InvalidWorkbook('Invalid shared string reference.') from error
    return value.text


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    return [''.join(item.itertext()) for item in root.findall('m:si', NS)]


def _mapping_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    relationship_id = None
    for sheet in workbook.findall('m:sheets/m:sheet', NS):
        if sheet.get('name') == 'Mapping Proposal':
            relationship_id = sheet.get(f'{{{NS["r"]}}}id')
            break
    if not relationship_id:
        raise InvalidWorkbook('Missing "Mapping Proposal" worksheet.')
    relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
    for rel in relationships.findall('p:Relationship', NS):
        if rel.get('Id') == relationship_id:
            target = rel.get('Target', '')
            if rel.get('TargetMode') == 'External':
                raise InvalidWorkbook('External worksheet reference is not supported.')
            from posixpath import normpath
            path = normpath(target.lstrip('/') if target.startswith('/') else f'xl/{target}')
            if not path.startswith('xl/worksheets/') or '..' in path.split('/'):
                raise InvalidWorkbook('Invalid mapping worksheet reference.')
            return path
    raise InvalidWorkbook('Cannot locate the Mapping Proposal worksheet.')


def _rows(archive: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> dict[int, dict[int, str]]:
    root = ET.fromstring(archive.read(sheet_path))
    result: dict[int, dict[int, str]] = {}
    for row in root.findall('.//m:sheetData/m:row', NS):
        try:
            index = int(row.get('r', '0'))
        except ValueError as error:
            raise InvalidWorkbook('Invalid worksheet row number.') from error
        if index < 2:
            continue
        cells = {}
        for cell in row.findall('m:c', NS):
            value = _text(cell, shared).strip()
            if value:
                cells[_column_number(cell.get('r', ''))] = value[:MAX_CELL_LENGTH]
        if cells:
            result[index] = cells
        if len(result) > MAX_MAPPING_ROWS + 2:
            raise InvalidWorkbook(f'Too many rows; maximum {MAX_MAPPING_ROWS} mapping rows.')
    return result


def read_mapping_proposal(contents: bytes) -> list[dict[str, str]]:
    """Return nonempty mapping rows from the upload, with original row numbers."""
    if not contents or len(contents) > MAX_FILE_BYTES:
        raise InvalidWorkbook('Excel file is empty or exceeds the 5 MB limit.')
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise InvalidWorkbook('Workbook exceeds the decompressed size limit.')
            shared = _shared_strings(archive)
            worksheet = _mapping_sheet_path(archive)
            rows = _rows(archive, worksheet, shared)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise InvalidWorkbook('Invalid or unsupported .xlsx workbook.') from error

    headers = {number: name for number, name in rows.get(2, {}).items()}
    if not REQUIRED_HEADERS.issubset(set(headers.values())):
        missing = sorted(REQUIRED_HEADERS - set(headers.values()))
        raise InvalidWorkbook(f'Missing required column(s): {", ".join(missing)}')

    result = []
    for row_number, columns in sorted(rows.items()):
        if row_number < 3:
            continue
        record = {header: columns.get(number, '') for number, header in headers.items() if header in FIELDS}
        if not any(record.values()):
            continue
        record['excel_row'] = row_number
        result.append(record)
        if len(result) > MAX_MAPPING_ROWS:
            raise InvalidWorkbook(f'Too many mappings; maximum {MAX_MAPPING_ROWS}.')
    if not result:
        raise InvalidWorkbook('No mapping rows found in the Mapping Proposal worksheet.')
    return result


def simple_stats(records: list[dict]) -> dict:
    """Non-judgmental overview; actual approval is decided by Gemini."""
    return {
        'mappings': len(records),
        'rule_types': dict(Counter(item.get('Proposed rule type', '') for item in records)),
        'missing_target_names': sum(not item.get('Target field name') for item in records),
        'unresolved_review_rows': sum(item.get('Requires review', '').lower() in {'yes', 'true', '1'}
                                      and not item.get('Reviewer decision') for item in records),
    }
