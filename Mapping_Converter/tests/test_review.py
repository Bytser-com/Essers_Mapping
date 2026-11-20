"""No live AI requests: test Excel parsing and API behavior with a mocked reviewer."""

import io
import zipfile

from fastapi.testclient import TestClient

import api
from scripts.excel_review import InvalidWorkbook, read_mapping_proposal

CLIENT = TestClient(api.app)
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def example_xlsx(*, rule="DIRECT", source="/Order/Id", fixed=""):
    headers = ["Mapping ID", "Target field name", "Source full path", "Proposed rule type", "Fixed value"]
    values = ["MP-001", "ID", source, rule, fixed]

    def row(number, cells):
        import html

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


def test_read_excel_fields():
    records = read_mapping_proposal(example_xlsx())
    assert len(records) == 1
    assert records[0]["Source full path"] == "/Order/Id"
    assert records[0]["excel_row"] == 3


def test_case_insensitive_sheet_name():
    # Replace 'Mapping Proposal' with lowercase 'mapping proposal'
    raw_xlsx = example_xlsx()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw_xlsx), "r") as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b'name="Mapping Proposal"', b'name="mapping proposal"')
            zout.writestr(item, content)

    records = read_mapping_proposal(buf.getvalue())
    assert len(records) == 1
    assert records[0]["Source full path"] == "/Order/Id"


def test_corrupt_workbook_rejected():
    try:
        read_mapping_proposal(b"not a workbook")
        raise AssertionError("Expected InvalidWorkbook")
    except InvalidWorkbook:
        pass


def test_api_accepts_review(monkeypatch):
    monkeypatch.setattr(
        "scripts.pipeline.review_with_gemini",
        lambda rows: {
            "decision": "ACCEPTED",
            "summary": "Looks consistent",
            "findings": [],
            "checked_mappings": len(rows),
        },
    )
    monkeypatch.setattr(
        "api.download_proposal_excel_from_sftp",
        lambda company, version, proposal_type, **kwargs: (
            example_xlsx(),
            f"/Proposals/{company}/{version}/{proposal_type}/MProposal-Nouryon_V2.xlsx",
        ),
    )
    response = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 200
    assert response.json()["decision"] == "ACCEPTED"
    assert response.json()["checked_mappings"] == 1


def test_api_returns_rejection(monkeypatch):
    monkeypatch.setattr(
        "scripts.pipeline.review_with_gemini",
        lambda rows: {
            "decision": "REJECTED",
            "summary": "Contradictory rule",
            "findings": ["Row 3: DIRECT mapping has no source"],
            "checked_mappings": len(rows),
        },
    )
    monkeypatch.setattr(
        "api.download_proposal_excel_from_sftp",
        lambda company, version, proposal_type, **kwargs: (
            example_xlsx(source=""),
            f"/Proposals/{company}/{version}/{proposal_type}/MProposal-Nouryon_V2.xlsx",
        ),
    )
    response = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 200
    assert response.json()["decision"] == "REJECTED"


def test_api_missing_parameters():
    # Missing companyName
    res1 = CLIENT.post("/review-excel?type=inbound&versionNumber=v2")
    assert res1.status_code == 422

    # Missing type
    res2 = CLIENT.post("/review-excel?companyName=nouryon&versionNumber=v2")
    assert res2.status_code == 422

    # Missing versionNumber
    res3 = CLIENT.post("/review-excel?companyName=nouryon&type=inbound")
    assert res3.status_code == 422

    # No query params at all
    res4 = CLIENT.post("/review-excel")
    assert res4.status_code == 422


def test_api_empty_parameters():
    # Empty companyName
    res1 = CLIENT.post("/review-excel?companyName=&type=inbound&versionNumber=v2")
    assert res1.status_code in (400, 422)

    # Whitespace type
    res2 = CLIENT.post("/review-excel?companyName=nouryon&type=%20%20&versionNumber=v2")
    assert res2.status_code == 400
    assert "type" in res2.json()["detail"].lower()

    # Whitespace versionNumber
    res3 = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=%20")
    assert res3.status_code == 400
    assert "versionnumber" in res3.json()["detail"].lower()


def test_api_sftp_file_not_found(monkeypatch):
    from sftp_service import SftpFileNotFoundError

    def not_found(*args, **kwargs):
        raise SftpFileNotFoundError("File not found on SFTP")

    monkeypatch.setattr("api.download_proposal_excel_from_sftp", not_found)
    response = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_api_sftp_connection_error(monkeypatch):
    from sftp_service import SftpError

    def conn_err(*args, **kwargs):
        raise SftpError("Connection refused")

    monkeypatch.setattr("api.download_proposal_excel_from_sftp", conn_err)
    response = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 502
    assert "sftp" in response.json()["detail"].lower()


def test_api_corrupt_file_from_sftp(monkeypatch):
    monkeypatch.setattr(
        "api.download_proposal_excel_from_sftp",
        lambda *args, **kwargs: (b"not an excel", "/path/to/file.xlsx"),
    )
    response = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 422


def test_api_fail_closed(monkeypatch):
    from scripts.gemini_review import ReviewUnavailable

    def unavailable(_):
        raise ReviewUnavailable("not configured")

    monkeypatch.setattr(
        "api.download_proposal_excel_from_sftp",
        lambda *args, **kwargs: (example_xlsx(), "/path/to/file.xlsx"),
    )
    monkeypatch.setattr("scripts.pipeline.review_with_gemini", unavailable)
    response = CLIENT.post("/review-excel?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 503


def test_alias_endpoint_review(monkeypatch):
    monkeypatch.setattr(
        "scripts.pipeline.review_with_gemini",
        lambda rows: {
            "decision": "ACCEPTED",
            "summary": "Looks consistent",
            "findings": [],
            "checked_mappings": len(rows),
        },
    )
    monkeypatch.setattr(
        "api.download_proposal_excel_from_sftp",
        lambda *args, **kwargs: (example_xlsx(), "/path/to/file.xlsx"),
    )
    response = CLIENT.post("/review?companyName=nouryon&type=inbound&versionNumber=v2")
    assert response.status_code == 200
    assert response.json()["decision"] == "ACCEPTED"


def test_existing_endpoints():
    assert CLIENT.get("/health").json()["status"] == "ok"
    assert CLIENT.get("/").status_code == 200
