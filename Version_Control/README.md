# Version Control Service

The **Version Control Service** is a Java Spring Boot microservice within the Preparation Stage of the Essers Mapping Architecture. It interfaces with the shared SFTP fileshare (`sftp-shared`) to track, version, inspect, and retrieve customer mapping proposal files and their associated metadata.

---

## Table of Contents

- [Features](#features)
- [SFTP Fileshare Folder Structure](#sftp-fileshare-folder-structure)
  - [Directory Hierarchy](#directory-hierarchy)
  - [Companion `metadata.json`](#companion-metadatajson)
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
- **Metadata Support**: Reads companion `metadata.json` for creation timestamp, author, and description, with automatic fallback to file attributes.
- **Base64 File Streaming**: Delivers Excel spreadsheets (`.xlsx`, `.xls`) packaged inside JSON payloads for API clients and frontend UIs.
- **Security & Validation**: Strict input sanitation preventing directory traversal attacks (`..`, `/`, `\`). Case-insensitive folder resolution for cross-platform compatibility.

---

## SFTP Fileshare Folder Structure

### Directory Hierarchy

Proposal files are organized on the SFTP storage under the base directory (default `/Proposals/`), partitioned by company name and version folder:

```text
/Proposals/                                <-- Base directory (configurable via SFTP_BASE_PATH)
├── <CompanyA>/                            <-- Company name (e.g., VanRoey)
│   ├── v1/
│   │   ├── mappingproposal.xlsx           <-- Proposal Excel spreadsheet
│   │   └── metadata.json                  <-- Companion metadata file
│   ├── v2/
│   │   ├── mappingproposal.xlsx
│   │   └── metadata.json
│   └── v3/
│       ├── mappingproposal.xlsx
│       └── metadata.json
└── <CompanyB>/
    └── v1/
        ├── proposal_b.xlsx
        └── metadata.json
```

### Companion `metadata.json`

Each version directory contains a `metadata.json` file providing structured context about that proposal release:

```json
{
  "company": "VanRoey",
  "version": "v3",
  "filename": "mappingproposal.xlsx",
  "createdDate": "2026-11-10T14:30:00Z",
  "createdBy": "Jane Doe",
  "description": "Updated warehouse pallet mapping rules"
}
```

### Version Ordering & Fallbacks

- **Version Resolution**: Versions are compared using `VersionComparator` so `v1` < `v2` < `v3` < `v10`.
- **Missing `metadata.json`**: If `metadata.json` is missing or corrupted, the service automatically detects the `.xlsx` or `.xls` file in the version folder and uses the SFTP file modification timestamp as fallback.
- **Case-Insensitive Resolution**: If an API consumer passes `company=vanroey&version=v3`, the service resolves the directory names even if they are stored as `VanRoey` and `V3`.

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

### 1. GET `/proposals`

Retrieves an overview of all companies with their **latest version** and associated metadata.

* **URL**: `/proposals` (or `/Proposals`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(optional, string)*: Filter results to a specific company (e.g. `?company=VanRoey`).

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
    "company": "Google",
    "latestVersion": "v2",
    "filename": "google_v2.xlsx",
    "fullPath": "/Proposals/Google/v2/google_v2.xlsx",
    "createdDate": "2026-11-10T12:00:00Z",
    "createdBy": "John Smith",
    "description": "Initial proposal"
  },
  {
    "company": "VanRoey",
    "latestVersion": "v3",
    "filename": "mappingproposal.xlsx",
    "fullPath": "/Proposals/VanRoey/v3/mappingproposal.xlsx",
    "createdDate": "2026-11-10T14:30:00Z",
    "createdBy": "Jane Doe",
    "description": "Updated warehouse pallet mapping rules"
  }
]
```

---

### 2. GET `/proposals/file`

Retrieves a specific proposal version for a company, returning the Excel file (encoded in Base64) along with its metadata.

* **URL**: `/proposals/file` (or `/Proposals/file`)
* **Method**: `GET`
* **Query Parameters**:
  * `company` *(required, string)*: Name of the company (e.g. `vanroey`).
  * `version` *(required, string)*: Version identifier (e.g. `v3`).

#### Response Codes

| Status Code | Description |
| :--- | :--- |
| `200 OK` | Successfully retrieved file and metadata. |
| `400 Bad Request` | Missing required query parameters or illegal path traversal characters. |
| `404 Not Found` | Company directory, version directory, or Excel file does not exist. |
| `502 Bad Gateway` / `500` | SFTP transfer failure or storage communication error. |

#### Example Request

```http
GET /proposals/file?company=vanroey&version=v3 HTTP/1.1
Host: localhost:8080
```

#### Example Response (`200 OK`)

```json
{
  "company": "VanRoey",
  "version": "v3",
  "filename": "mappingproposal.xlsx",
  "fullPath": "/Proposals/VanRoey/v3/mappingproposal.xlsx",
  "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sizeBytes": 14250,
  "createdDate": "2026-11-10T14:30:00Z",
  "createdBy": "Jane Doe",
  "description": "Updated warehouse pallet mapping rules",
  "fileContentBase64": "UEsDBBQAAAAIAAA..."
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
