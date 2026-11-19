# Mapping Converter Service

The **Mapping Converter Service** is a FastAPI microservice responsible for converting approved customer Excel mapping proposals into standardized JSON mapping packages.

These JSON mapping packages contain the exact `source_path` and `target_path` pairs required by the Runtime Engine (Java backend) to automatically process and convert incoming XML documents.

---

## Architecture & Responsibilities

- **Input**: Approved customer mapping proposal spreadsheet (`.xlsx` formatted according to the standard Nouryon layout).
- **Extraction**: Reads the `'Mapping Proposal'` sheet, extracting:
  - **Source Path**: `Source full path` (with fallback to `Source segment path` / `Source field name`).
  - **Target Path**: Combined `Target segment path` and `Target field name` (e.g. `/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_NUMB`).
- **Output**: JSON mapping package adhering to the schema expected by the Runtime Engine:
  ```json
  {
    "mappings": [
      {
        "source_path": "/DELVRY03/IDOC/E1EDL20/VBELN",
        "target_path": "/SHP_OBDLV_SAVE_REPLICA05/IDOC/E1BPOBDLVHDR/DELIV_NUMB"
      }
    ]
  }
  ```

---

## Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check endpoint returning `{"status": "ok", "service": "mapping-converter"}` |
| `GET` | `/` | Root service identifier message |
| `POST` | `/convert` | Accepts `multipart/form-data` with an Excel workbook (`.xlsx`) and returns the parsed JSON `MappingPackage` |

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
