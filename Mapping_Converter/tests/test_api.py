import io
from pathlib import Path
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Mapping Converter" in response.json()["message"]


def test_convert_valid_excel_upload():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mapping Proposal"
    ws.append(["Category"])
    ws.append(["Target segment path", "Target field name", "Source full path"])
    ws.append(["/DEST/HEADER", "DOC_NUM", "/SRC/HEADER/NUMBER"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    files = {
        "file": ("proposal.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    response = client.post("/convert", files=files)

    assert response.status_code == 200
    data = response.json()
    assert "mappings" in data
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["source_path"] == "/SRC/HEADER/NUMBER"
    assert data["mappings"][0]["target_path"] == "/DEST/HEADER/DOC_NUM"


def test_convert_sample_nouryon_proposal():
    proposal_path = (
        Path(__file__).resolve().parents[2] / "data/shared-sftp/Proposals/nouryon/v4/MProposal-Nouryon_V4.xlsx"
    )
    if not proposal_path.exists():
        return

    with open(proposal_path, "rb") as f:
        files = {
            "file": (
                "MProposal-Nouryon_V4.xlsx",
                f.read(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        response = client.post("/convert", files=files)

    assert response.status_code == 200
    data = response.json()
    assert len(data["mappings"]) == 5


def test_convert_rejects_non_excel_file():
    files = {"file": ("data.txt", b"plain text", "text/plain")}
    response = client.post("/convert", files=files)
    assert response.status_code == 400
    assert "Only Excel files" in response.json()["detail"]


def test_convert_rejects_empty_file():
    files = {"file": ("empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = client.post("/convert", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_convert_rejects_corrupted_excel():
    files = {
        "file": (
            "corrupt.xlsx",
            b"not a zip or excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/convert", files=files)
    assert response.status_code == 400
    assert "Failed to parse Excel workbook" in response.json()["detail"]


def test_convert_and_upload_success():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mapping Proposal"
    ws.append(["Target segment path", "Target field name", "Source full path"])
    ws.append(["/SHP_HEADER", "DOC_ID", "/SRC_HEADER/NUM"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    files = {
        "file": ("proposal.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    data = {
        "company": "Nouryon",
        "version": "v4",
        "message_type": "outbound",
        "user_created": "analist_a",
        "package_version": "1.0.0",
    }

    with patch(
        "api.save_mapping_package_to_sftp", return_value="/Packages/nouryon/v4/outbound/MPackage.json"
    ) as mock_save:
        response = client.post("/convert-and-upload", files=files, data=data)

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["sftp_path"] == "/Packages/nouryon/v4/outbound/MPackage.json"
    assert res_data["company"] == "nouryon"
    assert res_data["version"] == "v4"
    assert res_data["message_type"] == "outbound"
    assert res_data["filename"] == "MPackage.json"
    assert res_data["mapping_count"] == 1
    assert res_data["package"]["schema_version"] == "1.0"
    assert mock_save.called


def test_convert_and_upload_validation_errors():
    files = {"file": ("test.xlsx", b"some bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    # Missing company
    res = client.post(
        "/convert-and-upload", files=files, data={"company": "   ", "version": "v1", "message_type": "inbound"}
    )
    assert res.status_code == 400
    assert "company" in res.json()["detail"].lower()
