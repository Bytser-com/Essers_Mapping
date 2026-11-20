"""No live AI requests: test Excel parsing and API behavior with a mocked reviewer."""

import io
import zipfile

from fastapi.testclient import TestClient

import api
from excel_review import InvalidWorkbook, read_mapping_proposal

CLIENT = TestClient(api.app)
MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def example_xlsx(*, rule='DIRECT', source='/Order/Id', fixed=''):
    headers = ['Mapping ID', 'Target field name', 'Source full path', 'Proposed rule type', 'Fixed value']
    values = ['MP-001', 'ID', source, rule, fixed]
    def row(number, cells):
        import html
        parts = []
        for column, value in enumerate(cells):
            if value:
                letter = chr(ord('A') + column)
                parts.append(f'<c r="{letter}{number}" t="inlineStr"><is><t>{html.escape(value)}</t></is></c>')
        return f'<row r="{number}">{"".join(parts)}</row>'
    sheet = (f'<worksheet xmlns="{MAIN_NS}"><sheetData>'
             + row(2, headers) + row(3, values) + '</sheetData></worksheet>')
    workbook = (f'<workbook xmlns="{MAIN_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Mapping Proposal" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as zipf:
        zipf.writestr('xl/workbook.xml', workbook)
        zipf.writestr('xl/_rels/workbook.xml.rels', rels)
        zipf.writestr('xl/worksheets/sheet1.xml', sheet)
    return out.getvalue()


def test_read_excel_fields():
    records = read_mapping_proposal(example_xlsx())
    assert len(records) == 1
    assert records[0]['Source full path'] == '/Order/Id'
    assert records[0]['excel_row'] == 3


def test_corrupt_workbook_rejected():
    try:
        read_mapping_proposal(b'not a workbook')
        raise AssertionError('Expected InvalidWorkbook')
    except InvalidWorkbook:
        pass


def test_api_accepts_review(monkeypatch):
    monkeypatch.setattr(api, 'review_with_gemini', lambda rows: {
        'decision': 'ACCEPTED', 'summary': 'Looks consistent',
        'findings': [], 'checked_mappings': len(rows),
    })
    response = CLIENT.post('/review-excel', files={
        'file': ('proposal.xlsx', example_xlsx(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    })
    assert response.status_code == 200
    assert response.json()['decision'] == 'ACCEPTED'
    assert response.json()['checked_mappings'] == 1


def test_api_returns_rejection(monkeypatch):
    monkeypatch.setattr(api, 'review_with_gemini', lambda rows: {
        'decision': 'REJECTED', 'summary': 'Contradictory rule',
        'findings': ['Row 3: DIRECT mapping has no source'], 'checked_mappings': len(rows),
    })
    response = CLIENT.post('/review-excel', files={'file': ('proposal.xlsx', example_xlsx(source=''), 'application/octet-stream')})
    assert response.status_code == 200
    assert response.json()['decision'] == 'REJECTED'


def test_api_wrong_extension():
    response = CLIENT.post('/review-excel', files={'file': ('mapping.csv', b'hello', 'text/csv')})
    assert response.status_code == 400


def test_api_corrupt_file():
    response = CLIENT.post('/review-excel', files={'file': ('mapping.xlsx', b'bad', 'application/octet-stream')})
    assert response.status_code == 422


def test_api_fail_closed(monkeypatch):
    from gemini_review import ReviewUnavailable
    def unavailable(_):
        raise ReviewUnavailable('not configured')
    monkeypatch.setattr(api, 'review_with_gemini', unavailable)
    response = CLIENT.post('/review-excel', files={'file': ('proposal.xlsx', example_xlsx(), 'application/octet-stream')})
    assert response.status_code == 503


def test_existing_endpoints():
    assert CLIENT.get('/health').json()['status'] == 'ok'
    assert CLIENT.get('/').status_code == 200
