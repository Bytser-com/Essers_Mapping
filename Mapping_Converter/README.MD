# Mapping Converter Service

The **Mapping Converter Service** is a FastAPI microservice in the H.Essers Mapping Platform. It is responsible for parsing approved customer Excel mapping proposals into standardized JSON mapping packages and uploading them directly to the shared SFTP storage (`sftp-shared`).

These JSON mapping packages contain the exact `source_path` and `target_path` pairs required by the Runtime Engine (Java backend) to automatically process and convert incoming customer XML documents into the standardized H.Essers logistics schemas.

---

## Architecture & Role

```mermaid
flowchart TD
    Client["Analyst / Frontend UI"]
    Converter["Mapping Converter Service (FastAPI)<br/>Port 8001"]
    SFTP["Shared SFTP (sftp-shared)<br/>Port 2222 / WebUI 8081"]
    Runtime["Runtime Engine (Java Backend)<br/>Port 8080"]

    Client -->|"POST /convert-and-upload<br/>(Excel proposal .xlsx)"| Converter
    Converter -->|"1. Parse Excel"| Converter
    Converter -->|"2. Write MPackage.json"| SFTP
    SFTP -->|"3. Read MPackage.json<br/>(/Packages/<client>/<v>/<type>/)"| Runtime
    Runtime -->|"4. Transform Customer XML<br/>to H.Essers Schema"| Runtime
```

### Responsibilities:
- **Input**: Approved customer mapping proposal spreadsheet (`.xlsx` formatted according to the standard Nouryon layout).
- **Extraction**: Reads the `'Mapping Proposal'` sheet, extracting:
  - **Source Path**: `Source full path` (with fallback to `Source segment path` / `Source field name`).
  - **Target Path**: Combined `Target segment path` and `Target field name` (e.g. `/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_NUMB`).
- **Metadata Generation**: Adds a header containing `schema_version` and `meta` (client name, package version, message type, UTC creation date, author).
- **Output**: Standardized JSON mapping package adhering to the schema expected by the Runtime Engine.
- **SFTP Storage**: Writes the resulting JSON directly to the shared SFTP server under the standardized directory structure:
  ```
  /Packages/<companyName>/<version>/<type>/MPackage.json
  ```

---

## Output JSON Schema & Example

The output JSON mapping package places metadata and version information at the top of the file:

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
    },
    {
      "source_path": "/DELVRY03/IDOC/E1EDL20/E1EDT13/NTANF",
      "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1SHP_OBDLV_SAVE_REPLICA/E1BPDLVDEADLN/TIMESTAMP_UTC"
    }
  ]
}
```

---

## SFTP Directory Structure & Naming Conventions

Remote directory layout on the shared SFTP server (`sftp-shared`):

```
/Packages
└── <companyName>
    └── <version>
        └── <message_type>
            └── MPackage.json
```

### Examples:
| Type | Full SFTP Path |
| :--- | :--- |
| **Inbound** | `/Packages/nouryon/v3/inbound/MPackage.json` |
| **Outbound** | `/Packages/nouryon/v4/outbound/MPackage.json` |

- **Folder version normalization**: Versions are automatically normalized to `v<N>` (e.g., `"4"`, `"V4"`, or `"v4"` become `"v4"`).
- **Company & Type normalization**: Slugs are lowercase and trimmed (e.g., `"Nouryon "` becomes `"nouryon"`).

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check endpoint returning `{"status": "ok", "service": "mapping-converter"}` |
| `GET` | `/` | Service root identifier message |
| `POST` | `/convert-and-upload` | **(Main)** Converts Excel proposal, attaches metadata header, and uploads `MPackage.json` to SFTP |
| `POST` | `/convert/save` | Alias for `/convert-and-upload` |
| `POST` | `/convert` | **(Dry-run / Preview)** Converts Excel proposal to JSON without uploading to SFTP |

### Detailed Specification for `POST /convert-and-upload`:

- **Content-Type**: `multipart/form-data`
- **Request Parameters**:
  - `file` *(UploadFile, required)*: The Excel proposal workbook (`.xlsx` or `.xls`).
  - `company` *(string, required)*: Customer / client name (e.g. `nouryon`).
  - `version` *(string, required)*: Version identifier (e.g. `v4`, `4`, or `1.0.0`).
  - `message_type` *(string, required)*: Message flow type (e.g. `inbound` or `outbound`).
  - `user_created` *(string, optional, default: `"analist_a"`)*: Analyst or author username.
  - `package_version` *(string, optional)*: Explicit semantic version override (defaults to e.g. `1.0.0` or `<version>.0.0`).

- **Responses**:
  - `201 Created`: Mapping package converted and successfully stored on SFTP.
  - `400 Bad Request`: Invalid file format (non-Excel), empty file, or missing parameters.
  - `502 Bad Gateway`: Unable to connect or authenticate to the SFTP server.

---

## Environment Variables & Configuration

The service uses environment variables from `../.env` or system environment. Sensible defaults are included for local Docker development:

| Variable | Local Default | Production (K8s) | Description |
| :--- | :--- | :--- | :--- |
| `SFTP_SHARED_HOST` | `localhost` | `sftp-shared` | Hostname of the SFTP server (`"none"` for local file fallback) |
| `SFTP_SHARED_PORT` | `2222` | `22` | SSH/SFTP port |
| `SFTP_SHARED_USER` | `shareduser` | `shareduser` | SFTP username |
| `SFTP_SHARED_PASSWORD` | `devpassword` | *(from Secret)* | SFTP password |
| `SFTP_SHARED_PACKAGES_DIR` | `/Packages` | `/Packages` | Base remote directory for mapping packages |
| `SFTP_ALLOW_UNKNOWN_KEYS` | `true` | `true` | Accept SFTP host keys automatically |

---

## Local Development Guide

### 1. Install Dependencies
Make sure you are using Python 3.12+ (or 3.14):

```bash
cd Mapping_Converter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the Local SFTP Storage (Docker)
The service expects the shared SFTP server to be running:

```bash
docker compose -f ../Scripts/docker-compose.sftp.yml up -d
```
*(If your user is not yet in the docker group, run with `sudo`)*.

- **SFTP Endpoint**: `localhost:2222` (`shareduser` / `devpassword`)
- **Web File Manager**: [http://localhost:8081](http://localhost:8081)

### 3. Start the Converter Service
Run Uvicorn with auto-reload on port **8001**:

```bash
uvicorn api:app --reload --port 8001
```

The service will be available at:
- **API Base**: `http://localhost:8001`
- **Swagger Documentation**: [http://localhost:8001/docs](http://localhost:8001/docs)

### 4. Stop the SFTP Storage
When finished:

```bash
docker compose -f ../Scripts/docker-compose.sftp.yml down
```
*(Add `-v` to wipe test volumes and uploaded packages: `docker compose -f ../Scripts/docker-compose.sftp.yml down -v`)*.

---

## Usage Examples

### A. Via cURL (Upload to SFTP)
```bash
curl -X POST "http://localhost:8001/convert-and-upload" \
  -F "file=@../Mapping_Proposal/templates/mapping_template.xlsx" \
  -F "company=nouryon" \
  -F "version=v4" \
  -F "message_type=outbound" \
  -F "user_created=analist_a"
```

### B. Via cURL (Dry-Run / Preview JSON Only)
```bash
curl -X POST "http://localhost:8001/convert" \
  -F "file=@../Mapping_Proposal/templates/mapping_template.xlsx"
```

### C. Programmatic Python Call
```python
from converter import convert_excel_to_sftp

package, sftp_path = convert_excel_to_sftp(
    excel_source="proposal.xlsx",
    company="nouryon",
    version="v4",
    message_type="outbound",
    user_created="analist_a",
)

print(f"Uploaded mapping package to: {sftp_path}")
print(f"Total mappings: {len(package.mappings)}")
```

---

## Running Automated Tests

Run the full pytest suite with branch coverage:

```bash
cd Mapping_Converter
pytest -v --cov=. --cov-branch --cov-report=term-missing
```

### Test Structure:
- `tests/test_api.py`: Tests FastAPI endpoints (`/health`, `/`, `/convert`, `/convert-and-upload`, input validation, error handling).
- `tests/test_converter.py`: Tests Excel parsing, sheet detection, path extraction, and fallbacks.
- `tests/test_sftp_service.py`: Tests slug normalization, semantic versioning, path building, SFTP folder creation, and Paramiko uploads.
