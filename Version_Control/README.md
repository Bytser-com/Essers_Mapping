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
  - [3. GET `/proposals/filedata`](#3-get-proposalsfiledata)
  - [4. PUT `/proposals/file`](#4-put-proposalsfile)
  - [5. POST `/proposals`](#5-post-proposals)
  - [6. DELETE `/proposals`](#6-delete-proposals)
- [How to Run Locally](#how-to-run-locally)
- [How to Test](#how-to-test)

---

## Features

- **SFTP Integration**: Communicates with the remote SFTP share via Spring Integration SFTP without needing a local persistent mount.
- **Natural Versioning**: Employs a semantic/numeric version comparator ensuring natural version ordering (e.g. `v10` is recognized as newer than `v3`).
- **Proposal Type Categorization**: Supports proposal types (e.g., `inbound`, `outbound`, `inboud-accept`) under `/Proposals/<companyName>/<version>/<proposalType>/`. Proposal type inputs are case-insensitive and normalized to lowercase; all API responses, SFTP directory resolution, and persisted metadata use lowercase proposal types.
- **Metadata Support**: Reads companion `proposal.json` (or `metadata.json`) for creation timestamp, author, description, workflow status, proposal type, and AI status, with automatic fallback to file attributes.
- **Base64 File Streaming**: Delivers Excel spreadsheets (`.xlsx`, `.xls`) packaged inside JSON payloads for API clients and frontend UIs.
- **Security & Validation**: Strict input sanitation preventing directory traversal attacks (`..`, `/`, `\`). Case-insensitive folder resolution for cross-platform compatibility. Parameter length validation enforcing a maximum of 20 characters on `company` and `proposalType` / `proposal_type`.

---

## SFTP Fileshare Folder Structure

### Directory Hierarchy

Proposal files are organized on the SFTP storage under the base directory (default `/Proposals/`), partitioned by customer slug, version folder, and proposal type:

```text
/Proposals/                                <-- Base directory (configurable via SFTP_BASE_PATH)
├── <customer-slug>/                       <-- Customer directory (e.g., nouryon, voorbeeldbedrijf-c)
│   ├── v1/
│   │   └── <proposal-type>/               <-- Proposal type folder (e.g., inbound, outbound)
│   │       ├── MProposal-Nouryon_V1.xlsx  <-- Proposal Excel spreadsheet (pattern: MProposal-<Customer>_V<N>.xlsx)
│   │       └── proposal.json              <-- Companion metadata file (or metadata.json)
│   ├── v2/
│   │   └── <proposal-type>/
│   │       ├── MProposal-Nouryon_V2.xlsx
│   │       └── proposal.json
│   └── v3/
│       └── <proposal-type>/
│           ├── MProposal-Nouryon_V3.xlsx
│           └── proposal.json
└── <another-customer>/
    └── v1/
        └── <proposal-type>/
            ├── MProposal-Customer_V1.xlsx
            └── proposal.json
```

### Companion Metadata (`proposal.json` / `metadata.json`)

Each proposal type directory contains a companion metadata JSON file (`proposal.json` written by the AI pipeline, or `metadata.json`) providing structured context and status for that proposal release:

```json
{
  "customer": "Nouryon",
  "company": "Nouryon",
  "version": "v2",
  "proposal_type": "inbound",
  "proposalType": "inbound",
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
- **`proposal_type` / `proposalType`**: Proposal category / type (e.g., `"inbound"`, `"outbound"`, `"inboud-accept"`).
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
- **Proposal Type Subdirectory**: Proposals are organized inside `<proposalType>` subfolders within each version. For backward compatibility with legacy storage layouts, versions containing files directly inside the version folder are also supported.
- **Metadata Fallbacks**: The service checks for `metadata.json` first, then falls back to `proposal.json` (both case-insensitive). If metadata is missing or invalid, the version is skipped in the `GET /proposals` overview to prevent broken entries, but can still be fetched directly via `GET /proposals/file` with fallback to file modification timestamps.
- **Excel File Resolution**: The service first looks for the file named in `metadata.filename`. If not specified or absent, it automatically detects the first non-directory file ending with `.xlsx` or `.xls`.
- **Case-Insensitive Resolution**: If an API consumer passes `company=nouryon&version=v2&proposalType=INBOUND` (or `proposal_type=Inbound`), the service resolves the directory names case-insensitively on disk (e.g. matching `Inbound` or `inbound`), normalizes `proposalType` to lowercase, and returns lowercase `proposalType` across all API responses and metadata files.

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

Retrieves an overview of all companies with their **latest version**, `proposalType`, and associated metadata.

* **URL**: `/proposals` (or `/Proposals`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(optional, string, max 20 chars)*: Filter results to a specific company (e.g. `?company=nouryon`).
  * `proposalType` or `proposal_type` *(optional, string, max 20 chars, case-insensitive)*: Filter results to a specific proposal type (e.g. `?proposalType=inbound` or `?proposal_type=INBOUND`). Always normalized to lowercase.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved proposal overview list. |
| `400 Bad Request` | Parameter exceeds maximum length of 20 characters (`company` or `proposalType`/`proposal_type`), or contains illegal path traversal characters (`..`, `/`, `\`). |
| `404 Not Found` | A specific company was requested but does not exist or has no versions. |
| `502 Bad Gateway` / `500` | Failed to connect or read from SFTP storage (`StorageException`). |

#### Example Response (`200 OK`)

```json
[
  {
    "company": "nouryon",
    "latestVersion": "v2",
    "filename": "MProposal-Nouryon_V2.xlsx",
    "fullPath": "/Proposals/nouryon/v2/inbound/MProposal-Nouryon_V2.xlsx",
    "createdDate": "2026-11-12T14:30:00+00:00",
    "createdBy": "AI Pipeline",
    "description": "Generated mapping proposal",
    "status": "READY_FOR_REVIEW",
    "aiStatus": null,
    "customerName": "Nouryon",
    "proposalType": "inbound"
  },
  {
    "company": "voorbeeldbedrijf-c",
    "latestVersion": "v1",
    "filename": "MProposal-VoorbeeldbedrijfC_V1.xlsx",
    "fullPath": "/Proposals/voorbeeldbedrijf-c/v1/outbound/MProposal-VoorbeeldbedrijfC_V1.xlsx",
    "createdDate": "2026-10-20T16:45:00+02:00",
    "createdBy": null,
    "description": null,
    "status": "AI_CHECKING_REVIEW",
    "aiStatus": "RUNNING",
    "customerName": "Voorbeeldbedrijf C",
    "proposalType": "outbound"
  }
]
```

---

### 2. GET `/proposals/file`

Retrieves a specific proposal version for a company, returning the Excel file (encoded in Base64) along with its metadata.

* **URL**: `/proposals/file` (or `/Proposals/file`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(required, string, max 20 chars)*: Name of the company (e.g. `nouryon`).
  * `version` *(required, string)*: Version identifier (e.g. `v2`).
  * `proposalType` or `proposal_type` *(required, string, max 20 chars, case-insensitive)*: Proposal type (e.g. `inbound`). Both camelCase and snake_case parameter names are accepted; values are case-insensitive and normalized to lowercase.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved file and metadata. |
| `400 Bad Request` | Missing required query parameters, blank values, parameter exceeding 20 characters (`company` or `proposalType`/`proposal_type`), or illegal path traversal characters. |
| `404 Not Found` | Company directory, version directory, proposal type directory, or Excel file does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or storage communication error. |

#### Example Request

```http
GET /proposals/file?company=nouryon&version=v2&proposalType=inbound HTTP/1.1
Host: localhost:8080
```

#### Example Response (`200 OK`)

```json
{
  "company": "nouryon",
  "version": "v2",
  "filename": "MProposal-Nouryon_V2.xlsx",
  "fullPath": "/Proposals/nouryon/v2/inbound/MProposal-Nouryon_V2.xlsx",
  "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sizeBytes": 14250,
  "createdDate": "2026-11-12T14:30:00+00:00",
  "createdBy": "AI Pipeline",
  "description": "Generated mapping proposal",
  "fileContentBase64": "UEsDBBQAAAAIAAA...",
  "proposalType": "inbound"
}
```

---

### 3. GET `/proposals/filedata`

Retrieves parsed proposal file metadata, `proposalType`, and row mappings from the Excel file as structured JSON.

* **URL**: `/proposals/filedata` (or `/Proposals/filedata`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(required, string, max 20 chars)*: Name of the company (e.g. `bedrijfsnaam`).
  * `version` *(required, string)*: Version identifier (e.g. `versie`).
  * `proposalType` or `proposal_type` *(required, string, max 20 chars, case-insensitive)*: Proposal type (e.g. `inbound`). Both camelCase and snake_case parameter names are accepted; values are case-insensitive and normalized to lowercase.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved and parsed file data and rows. |
| `400 Bad Request` | Missing required query parameters, blank values, parameter exceeding 20 characters (`company` or `proposalType`/`proposal_type`), or illegal path traversal characters. |
| `404 Not Found` | Company directory, version directory, proposal type directory, or Excel file does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or storage communication error. |

#### Example Request

```http
GET /Proposals/filedata?company=bedrijfsnaam&version=versie&proposalType=inbound HTTP/1.1
Host: localhost:8080
```

#### Example Response (`200 OK`)

```json
{
  "version": "v1",
  "companyname": "Voorbeeldbedrijf C",
  "proposalType": "inbound",
  "upload_date": "2026-10-20",
  "upload_time": "16:45:00",
  "updated_time": "23:03:02",
  "updated_date": "2026-11-11",
  "createdBy": "Jane Doe",
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

Overwrites the current proposal Excel spreadsheet file on SFTP for a given company, version, and proposal type, updates `updated_date` and `updated_time` (and ISO `updated_at`) in `metadata.json` / `proposal.json`, and sets the status to `"In review"`.

* **URL**: `/proposals/file` (or `/Proposals/file`)
* **Method**: `PUT`
* **Query Parameters**:
  * `company` *(required, string, max 20 chars)*: Company name (e.g. `vanroey`). Case-insensitive lookup.
  * `version` *(required, string)*: Version string (e.g. `v3`). Case-insensitive lookup.
  * `proposalType` or `proposal_type` *(required, string, max 20 chars, case-insensitive)*: Proposal type (e.g. `inbound`). Case-insensitive lookup; both camelCase and snake_case parameter names are accepted, and metadata values are persisted in lowercase.
* **Request Body**:
  * Either `multipart/form-data` with part name `file` containing the `.xlsx` / `.xls` binary,
  * Or binary request body with `Content-Type: application/octet-stream` or `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Proposal file successfully replaced and metadata updated. |
| `400 Bad Request` | Missing query parameters, blank values, parameter exceeding 20 characters (`company` or `proposalType`/`proposal_type`), empty body, or corrupt non-Excel file. |
| `404 Not Found` | Company directory, version directory, or proposal type directory does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or remote write error. |

#### Example Request (`multipart/form-data`)

```http
PUT /Proposals/file?company=vanroey&version=v3&proposalType=inbound HTTP/1.1
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
  "fullPath": "/Proposals/VanRoey/v3/inbound/mappingproposal.xlsx",
  "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sizeBytes": 12480,
  "createdDate": "2026-11-10T12:00:00Z",
  "createdBy": "John Smith",
  "description": "Initial proposal",
  "fileContentBase64": "UEsDBBQAAAAIA...",
  "proposalType": "inbound"
}
```

---

### 5. POST `/proposals`

Approves a proposal for a given company, version, and proposal type.

> **Note**: This endpoint is currently a placeholder and returns `501 Not Implemented`.

* **URL**: `/proposals` (or `/Proposals`)
* **Method**: `POST`
* **Query Parameters**:
  * `company` *(required, string, max 20 chars)*: Company name (e.g. `vanroey`).
  * `version` *(required, string)*: Proposal version (e.g. `v3`).
  * `proposalType` or `proposal_type` *(required, string, max 20 chars, case-insensitive)*: Proposal type (e.g. `inbound`). Both camelCase and snake_case parameter names are accepted; values are case-insensitive and normalized to lowercase.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `501 Not Implemented` | The feature is planned and not implemented yet. |
| `400 Bad Request` | Missing required `company`, `version`, or `proposalType`/`proposal_type` parameter, or parameter exceeding 20 characters. |

#### Example Request

```http
POST /Proposals?company=vanroey&version=v3&proposalType=inbound HTTP/1.1
Host: localhost:8080
```

#### Example Response (`501 Not Implemented`)

```json
{
  "type": "about:blank",
  "title": "Not Implemented",
  "status": 501,
  "detail": "Approving proposal for company 'vanroey', version 'v3', and proposalType 'inbound' is not implemented yet",
  "instance": "/Proposals",
  "company": "vanroey",
  "version": "v3",
  "proposalType": "inbound",
  "timestamp": "2026-11-12T13:12:00Z"
}
```

---

### 6. DELETE `/proposals`

Deletes a proposal for a given company, version, and proposal type from the SFTP server. To prevent accidental deletions, the request body must contain a confirmation matching the company name.

* **URL**: `/proposals` (or `/Proposals`)
* **Method**: `DELETE`
* **Query Parameters**:
  * `company` *(required, string, max 20 chars)*: Company name (e.g. `vanroey`).
  * `version` *(required, string)*: Proposal version (e.g. `v2`).
  * `proposalType` or `proposal_type` *(required, string, max 20 chars, case-insensitive)*: Proposal type (e.g. `inbound`). Both camelCase and snake_case parameter names are accepted; values are case-insensitive and normalized to lowercase.
* **Request Body** (`application/json`):
  * `deleteCheck` *(required, string)*: Confirmation string that must match `company` exactly.

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `204 No Content` | Proposal successfully deleted. |
| `400 Bad Request` | Missing query parameters, parameter exceeding 20 characters (`company` or `proposalType`/`proposal_type`), missing body, or `deleteCheck` does not match `company`. |
| `404 Not Found` | Company, version, or proposal type directory does not exist. |
| `502 Bad Gateway` / `500` | SFTP storage error. |

#### Example Request

```http
DELETE /Proposals?company=vanroey&version=v2&proposalType=inbound HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "deleteCheck": "vanroey"
}
```

#### Example Response (`204 No Content`)

*(Empty response body)*

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
