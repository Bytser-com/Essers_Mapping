# Mapping Converter Service

The **Mapping Converter Service** is a FastAPI microservice responsible for converting approved customer Excel mapping proposals into standardized JSON mapping packages and optionally uploading them directly to the shared SFTP storage (`sftp-shared`).

These JSON mapping packages contain the exact `source_path` and `target_path` pairs required by the Runtime Engine (Java backend) to automatically process and convert incoming customer XML documents into the H.Essers standard format.

---

## Architecture & Responsibilities

- **Input**: Approved customer mapping proposal spreadsheet (`.xlsx` formatted according to the standard Nouryon layout).
- **Extraction**: Reads the `'Mapping Proposal'` sheet, extracting:
  - **Source Path**: `Source full path` (with fallback to `Source segment path` / `Source field name`).
  - **Target Path**: Combined `Target segment path` and `Target field name` (e.g. `/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_NUMB`).
- **Output**: Standardized JSON mapping package adhering to the schema expected by the Runtime Engine, including header metadata:
  ```json
  {
    "schema_version": "1.0",
    "meta": {
      "client_name": "nouryon",
      "package_version": "1.0.0",
      "package_type": "inbound",
      "date_created": "2024-06-19T12:00:00Z",
      "user_created": "analist_a"
    },
    "mappings": [
      {
        "source_path": "/DELVRY03/IDOC/E1EDL20/VBELN",
        "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_NUMB"
      }
    ]
  }
  ```
- **SFTP Storage**: Stores mapping packages on the shared SFTP server (`sftp-shared`) following the standardized directory structure:
  ```
  /Packages/<companyName>/<version>/<type>/MPackage.json
  ```
  *(e.g. `/Packages/nouryon/v3/inbound/MPackage.json`)*.

---

## SFTP Path Convention

| Scenario | Path Example |
| :--- | :--- |
| Inbound mapping package | `/Packages/nouryon/v3/inbound/MPackage.json` |
| Outbound mapping package | `/Packages/nouryon/v4/outbound/MPackage.json` |

---

## Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check endpoint returning `{"status": "ok", "service": "mapping-converter"}` |
| `GET` | `/` | Root service identifier message |
| `POST` | `/convert` | Accepts `multipart/form-data` with an Excel workbook (`.xlsx`) and returns the parsed JSON `MappingPackage` |
| `POST` | `/convert-and-upload` | Accepts Excel (`file`), `company`, `version`, `message_type`, optional `user_created` and `package_version`, parses the proposal, uploads the JSON to SFTP, and returns `SaveToSftpResponse` |

---

## Environment Variables

| Variable | Default (Local) | Production (Kubernetes) | Description |
| :--- | :--- | :--- | :--- |
| `SFTP_SHARED_HOST` | `localhost` | `sftp-shared` | Host of the shared SFTP server (set to 'none' for local file fallback) |
| `SFTP_SHARED_PORT` | `2222` | `22` | Port of the SFTP server |
| `SFTP_SHARED_USER` | `shareduser` | `shareduser` | SFTP username |
| `SFTP_SHARED_PASSWORD` | `devpassword` | *(from Secret)* | SFTP password |
| `SFTP_SHARED_PACKAGES_DIR` | `/Packages` | `/Packages` | Root remote folder on SFTP for mapping packages |
| `SFTP_ALLOW_UNKNOWN_KEYS` | `true` | `true` | Accept SFTP host keys |

---

## Local Development

### 1. Install Dependencies
```bash
cd Mapping_Converter
pip install -r requirements.txt
```

### 2. Start the Server
```bash
uvicorn api:app --reload --port 8001
```
Interactive Swagger documentation is available at `http://localhost:8001/docs`.

### 3. Run Tests
```bash
pytest -v --cov=. --cov-branch --cov-report=term-missing
```
