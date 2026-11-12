# Version Control Service

The **Version Control Service** is a Java Spring Boot microservice within the Preparation Stage of the Essers Mapping Architecture. It interfaces with the shared SFTP fileshare (`sftp-shared`) to track, version, inspect, and retrieve customer mapping proposal files and their associated metadata.

---

## Table of Contents

- [Features](#features)
- [SFTP Fileshare Folder Structure](#sftp-fileshare-folder-structure)
  - [Directory Hierarchy](#directory-hierarchy)
  - [Companion Metadata (`proposal.json` / `metadata.json`)](#companion-metadata-proposaljson--metadatajson)
  - [Version Ordering & Fallbacks](#version-ordering--fallbacks)
- [Environment Variables](#environment-variables)
- [API Endpoints Reference](#api-endpoints-reference)
  - [1. GET `/proposals`](#1-get-proposals)
  - [2. GET `/proposals/file`](#2-get-proposalsfile)
- [How to Run Locally](#how-to-run-locally)
- [How to Test](#how-to-test)

---

## Features

- **SFTP Integration**: Communicates with the remote SFTP share via Spring Integration SFTP without needing a local persistent mount.
- **Natural Versioning**: Employs a semantic/numeric version comparator ensuring natural version ordering (e.g. `v10` is recognized as newer than `v3`).
- **Metadata Support**: Reads companion `proposal.json` (or `metadata.json`) for creation timestamp, author, description, workflow status, and AI status, with automatic fallback to file attributes.
- **Base64 File Streaming**: Delivers Excel spreadsheets (`.xlsx`, `.xls`) packaged inside JSON payloads for API clients and frontend UIs.
- **Security & Validation**: Strict input sanitation preventing directory traversal attacks (`..`, `/`, `\`). Case-insensitive folder resolution for cross-platform compatibility.

---

## SFTP Fileshare Folder Structure

### Directory Hierarchy

Proposal files are organized on the SFTP storage under the base directory (default `/Proposals/`), partitioned by customer slug and version folder:

```text
/Proposals/                                <-- Base directory (configurable via SFTP_BASE_PATH)
├── <customer-slug>/                       <-- Customer directory (e.g., nouryon, voorbeeldbedrijf-c)
│   ├── v1/
│   │   ├── MProposal-Nouryon_V1.xlsx      <-- Proposal Excel spreadsheet (pattern: MProposal-<Customer>_V<N>.xlsx)
│   │   └── proposal.json                  <-- Companion metadata file (or metadata.json)
│   ├── v2/
│   │   ├── MProposal-Nouryon_V2.xlsx
│   │   └── proposal.json
│   └── v3/
│       ├── MProposal-Nouryon_V3.xlsx
│       └── proposal.json
└── <another-customer>/
    └── v1/
        ├── MProposal-Customer_V1.xlsx
        └── proposal.json
```

### Companion Metadata (`proposal.json` / `metadata.json`)

Each version directory contains a companion metadata JSON file (`proposal.json` written by the AI pipeline, or `metadata.json`) providing structured context and status for that proposal release:

```json
{
  "customer": "Nouryon",
  "company": "Nouryon",
  "version": "v2",
  "filename": "MProposal-Nouryon_V2.xlsx",
  "uploaded_at": "2026-11-12T14:30:00+00:00",
  "createdDate": "2026-11-12T14:30:00+00:00",
  "status": "READY_FOR_REVIEW",
  "ai_status": null,
  "createdBy": "AI Pipeline",
  "description": "Generated mapping proposal"
}
```

#### Supported Metadata Fields & Aliases:
- **`customer` / `company`**: Customer identifier or display name.
- **`version`**: Version identifier (e.g., `"v2"`).
- **`filename`**: Name of the generated Excel spreadsheet (e.g., `"MProposal-Nouryon_V2.xlsx"`). The backend prioritizes this filename when locating the proposal spreadsheet.
- **`uploaded_at` / `createdDate` / `created_date` / `uploadedAt`**: ISO 8601 creation/upload timestamp.
- **`status` / `proposal_status` / `proposalStatus`**: Proposal workflow status:
  - `AI_GENERATING`: Proposal generation in progress
  - `READY_FOR_REVIEW`: Completed and ready for reviewer inspection
  - `IN_REVIEW`: Currently under human review
  - `AI_CHECKING_REVIEW`: AI validation in progress
  - `RETURNED`: Proposal returned for revision
- **`ai_status` / `aiStatus`**: AI engine processing status:
  - `RUNNING`: AI background job is currently running
  - `FAILED`: AI job execution encountered an error
  - `null` / omitted: Idle / completed
- **`createdBy` / `created_by` / `creator`**: (Optional) Author or pipeline identity.
- **`description`**: (Optional) Free-text description of the proposal or change notes.

### Version Ordering & Fallbacks

- **Version Resolution**: Versions are compared using `VersionComparator` so `v1` < `v2` < `v3` < `v10`.
- **Metadata Fallbacks**: The service checks for `metadata.json` first, then falls back to `proposal.json` (both case-insensitive). If metadata is missing or invalid, the version is skipped in the `GET /proposals` overview to prevent broken entries, but can still be fetched directly via `GET /proposals/file` with fallback to file modification timestamps.
- **Excel File Resolution**: The service first looks for the file named in `metadata.filename`. If not specified or absent, it automatically detects the first non-directory file ending with `.xlsx` or `.xls`.
- **Case-Insensitive Resolution**: If an API consumer passes `company=nouryon&version=v2`, the service resolves the directory names even if they are stored with different casing on disk (e.g., `Nouryon/V2`).

---

## Environment Variables

Copy `.env.example` to `.env` or supply these environment variables:

| Variable | Description | Default | Kubernetes / Alternative |
| :--- | :--- | :--- | :--- |
| `SERVER_PORT` | HTTP server port | `8080` | — |
| `SFTP_HOST` | SFTP server hostname / IP | `localhost` | `SFTP_SHARED_HOST` |
| `SFTP_PORT` | SFTP port | `22` | `SFTP_SHARED_PORT` |
| `SFTP_USER` | SFTP username | `sftpuser` | `SFTP_SHARED_USER` |
| `SFTP_PASSWORD` | SFTP password | `sftppass` | `SFTP_SHARED_PASSWORD` |
| `SFTP_BASE_PATH` | Root directory on SFTP share | `/Proposals` | `SFTP_SHARED_PROPOSALS_DIR` |
| `SFTP_ALLOW_UNKNOWN_KEYS` | Allow unverified SSH host keys | `true` | — |

---

## API Endpoints Reference

All endpoints are mapped to both `/proposals` and `/Proposals`.

> [!NOTE]
> Interactive Swagger / OpenAPI UI is intentionally **not enabled** on this service in any environment (development, testing, or production). All endpoints, parameters, and response schemas are maintained directly in this specification document.

### 1. GET `/proposals`

Retrieves an overview of all companies with their **latest version** and associated metadata.

* **URL**: `/proposals` (or `/Proposals`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(optional, string)*: Filter results to a specific company (e.g. `?company=nouryon`).

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved proposal overview list. |
| `400 Bad Request` | Company parameter contains illegal path traversal characters (`..`, `/`, `\`). |
| `404 Not Found` | A specific company was requested but does not exist or has no versions. |
| `502 Bad Gateway` / `500` | Failed to connect or read from SFTP storage (`StorageException`). |

#### Example Response (`200 OK`)

```json
[
  {
    "company": "nouryon",
    "latestVersion": "v2",
    "filename": "MProposal-Nouryon_V2.xlsx",
    "fullPath": "/Proposals/nouryon/v2/MProposal-Nouryon_V2.xlsx",
    "createdDate": "2026-11-12T14:30:00+00:00",
    "createdBy": "AI Pipeline",
    "description": "Generated mapping proposal",
    "status": "READY_FOR_REVIEW",
    "aiStatus": null
  },
  {
    "company": "voorbeeldbedrijf-c",
    "latestVersion": "v1",
    "filename": "MProposal-VoorbeeldbedrijfC_V1.xlsx",
    "fullPath": "/Proposals/voorbeeldbedrijf-c/v1/MProposal-VoorbeeldbedrijfC_V1.xlsx",
    "createdDate": "2026-10-20T16:45:00+02:00",
    "createdBy": null,
    "description": null,
    "status": "AI_CHECKING_REVIEW",
    "aiStatus": "RUNNING"
  }
]
```

---

### 2. GET `/proposals/file`

Retrieves a specific proposal version for a company, returning the Excel file (encoded in Base64) along with its metadata.

* **URL**: `/proposals/file` (or `/Proposals/file`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(required, string)*: Name of the company (e.g. `nouryon`).
  * `version` *(required, string)*: Version identifier (e.g. `v2`).

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved file and metadata. |
| `400 Bad Request` | Missing required query parameters or illegal path traversal characters. |
| `404 Not Found` | Company directory, version directory, or Excel file does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or storage communication error. |

#### Example Request

```http
GET /proposals/file?company=nouryon&version=v2 HTTP/1.1
Host: localhost:8080
```

#### Example Response (`200 OK`)

```json
{
  "company": "nouryon",
  "version": "v2",
  "filename": "MProposal-Nouryon_V2.xlsx",
  "fullPath": "/Proposals/nouryon/v2/MProposal-Nouryon_V2.xlsx",
  "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sizeBytes": 14250,
  "createdDate": "2026-11-12T14:30:00+00:00",
  "createdBy": "AI Pipeline",
  "description": "Generated mapping proposal",
  "fileContentBase64": "UEsDBBQAAAAIAAA..."
}
```

---

### 3. GET `/proposals/filedata`

Retrieves parsed proposal file metadata and row mappings from the Excel file as structured JSON.

* **URL**: `/proposals/filedata` (or `/Proposals/filedata`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(required, string)*: Name of the company (e.g. `bedrijfsnaam`).
  * `version` *(required, string)*: Version identifier (e.g. `versie`).

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved and parsed file data and rows. |
| `400 Bad Request` | Missing required query parameters or illegal path traversal characters. |
| `404 Not Found` | Company directory, version directory, or Excel file does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or storage communication error. |

#### Example Request

```http
GET /Proposals/filedata?company=bedrijfsnaam&version=versie HTTP/1.1
Host: localhost:8080
```

#### Example Response (`200 OK`)

```json
{
  "version": "v1",
  "companyname": "Voorbeeldbedrijf C",
  "upload_date": "2026-10-20",
  "upload_time": "16:45:00",
  "updated_time": "23:03:02",
  "updated_date": "2026-11-11",
  "upload_user": "Jane Doe",
  "status": "READY_FOR_REVIEW",
  "rows": [
    {
      "source_field": "OrderNo",
      "target_field": "DeliveryNumber",
      "score": 95,
      "comment": "Direct semantic match"
    },
    {
      "source_field": null,
      "target_field": "root",
      "score": 95,
      "comment": "Target structure is fixed in the skill"
    }
  ]
}
```

---

### 4. PUT `/proposals/file`

Overwrites the current proposal Excel spreadsheet file on SFTP for a given company and version, updates `updated_date` and `updated_time` (and ISO `updated_at`) in `metadata.json` / `proposal.json`, and sets the status to `"In review"`.

* **URL**: `/proposals/file` (or `/Proposals/file`)
* **Method**: `PUT`
* **Query Parameters**:
  * `company` *(required, string)*: Company name (e.g. `vanroey`). Case-insensitive lookup.
  * `version` *(required, string)*: Version string (e.g. `v3`). Case-insensitive lookup.
* **Request Body**:
  * Either `multipart/form-data` with part name `file` containing the `.xlsx` / `.xls` binary,
  * Or binary request body with `Content-Type: application/octet-stream` or `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Proposal file successfully replaced and metadata updated. |
| `400 Bad Request` | Missing query parameters, empty body, or corrupt non-Excel file. |
| `404 Not Found` | Company directory, version directory, or proposal directory does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or remote write error. |

#### Example Request (`multipart/form-data`)

```http
PUT /Proposals/file?company=vanroey&version=v3 HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=boundary

--boundary
Content-Disposition: form-data; name="file"; filename="mappingproposal.xlsx"
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

<binary excel data>
--boundary--
```

#### Example Response (`200 OK`)

```json
{
  "company": "VanRoey",
  "version": "v3",
  "filename": "mappingproposal.xlsx",
  "fullPath": "/Proposals/VanRoey/v3/mappingproposal.xlsx",
  "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sizeBytes": 12480,
  "createdDate": "2026-11-10T12:00:00Z",
  "createdBy": "John Smith",
  "description": "Initial proposal",
  "fileContentBase64": "UEsDBBQAAAAIA..."
}
```

---

### 5. POST `/proposals`

Approves a proposal for a given company and version.

> **Note**: This endpoint is currently a placeholder and returns `501 Not Implemented`.

* **URL**: `/proposals` (or `/Proposals`)
* **Method**: `POST`
* **Query Parameters**:
  * `company` *(required, string)*: Company name (e.g. `vanroey`).
  * `version` *(required, string)*: Proposal version (e.g. `v3`).

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `501 Not Implemented` | The feature is planned and not implemented yet. |
| `400 Bad Request` | Missing required `company` or `version` parameter. |

#### Example Request

```http
POST /Proposals?company=vanroey&version=v3 HTTP/1.1
Host: localhost:8080
```

#### Example Response (`501 Not Implemented`)

```json
{
  "type": "about:blank",
  "title": "Not Implemented",
  "status": 501,
  "detail": "Approving proposal for company 'vanroey' and version 'v3' is not implemented yet",
  "instance": "/Proposals",
  "company": "vanroey",
  "version": "v3",
  "timestamp": "2026-11-12T13:12:00Z"
}
```

---

## How to Run Locally

### Prerequisites

- **Java 21+** (Eclipse Adoptium Temurin or OpenJDK)
- **Maven** (use the bundled `./mvnw` wrapper)
- A running SFTP server (or Docker SFTP container) matching your `.env` configuration.

### Steps

1. Navigate to the `Version_Control` directory:
   ```bash
   cd Version_Control
   ```
2. Copy `.env.example` to `.env` and set connection parameters:
   ```bash
   cp .env.example .env
   ```
3. Start the application:
   ```bash
   ./mvnw spring-boot:run
   ```
4. Verify the application is listening:
   ```bash
   curl http://localhost:8080/proposals
   ```

---

## How to Test

Run the full automated test suite using Maven:

```bash
# Run all unit and slice tests
./mvnw test

# Generate JaCoCo code coverage report
./mvnw test jacoco:report
```

The JaCoCo coverage report will be available at:
```text
Version_Control/target/site/jacoco-ut/index.html
```
