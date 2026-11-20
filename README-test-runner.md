
# Essers_Mapping — Running the Tests

This guide explains how to run the entire test suite or test individual components on **Windows (PowerShell)** and **Linux**.

All test runners and this README are located in the `Scripts/` directory.

Unless otherwise specified, commands are executed from the repository root (`Essers_Mapping/`).

## 1. Run All Tests

The test runner automatically executes all available tests and code quality checks across the project.

### Windows (PowerShell)

```powershell
.\Scripts\run-tests.cmd
```

Alternatively:

```powershell
python Scripts/run-tests.py
```

### Linux

```bash
bash Scripts/run-tests.sh
```

Alternatively:

```bash
python3 Scripts/run-tests.py
```

The runner continues executing checks even when individual tests fail. At the end, it displays a **PASS / FAIL / SKIP** summary.

If any check fails, the runner exits with code `1`.

### Useful Options

| Purpose | Windows | Linux |
|---|---|---|
| Run everything | `.\Scripts\run-tests.cmd` | `bash Scripts/run-tests.sh` |
| Skip Playwright E2E | `.\Scripts\run-tests.cmd --skip-e2e` | `bash Scripts/run-tests.sh --skip-e2e` |
| Only frontend build + E2E | `.\Scripts\run-tests.cmd --only-e2e` | `bash Scripts/run-tests.sh --only-e2e` |
| Show help | `python Scripts/run-tests.py --help` | `python3 Scripts/run-tests.py --help` |

**Note:** `--only-e2e` executes the frontend production build followed by the Playwright tests.

For individual project components, use the commands below.

---

## 2. Run Individual Tests

### A. Mapping Proposal — Python

**Windows:**

```powershell
cd Mapping_Proposal

python -m pytest -q
python -m ruff check .

cd ..
```

**Linux:**

```bash
cd Mapping_Proposal

python3 -m pytest -q
python3 -m ruff check .

cd ..
```

Optional formatting check:

```powershell
# Windows
cd Mapping_Proposal
python -m ruff format --check .
cd ..
```

```bash
# Linux
cd Mapping_Proposal
python3 -m ruff format --check .
cd ..
```

The formatting check is not included in the automatic test runner.

### B. Version Control — Java / Maven

**Windows:**

```powershell
cd Version_Control

.\mvnw.cmd clean verify

cd ..
```

**Linux:**

```bash
cd Version_Control

bash ./mvnw clean verify

cd ..
```

This compiles the Java application and runs its Maven tests and verification checks.

### C. Runtime — Java / Maven

**Windows:**

```powershell
cd Runtime

.\mvnw.cmd clean verify

cd ..
```

**Linux:**

```bash
cd Runtime

bash ./mvnw clean verify

cd ..
```

### D. Shared Scripts — Python & Node.js

Run these commands from the **repository root**.

**Windows:**

```powershell
python -m unittest discover -s Scripts/tests -p 'test_*.py'

node Scripts/tests/test_service_workflows.cjs
```

**Linux:**

```bash
python3 -m unittest discover -s Scripts/tests -p 'test_*.py'

node Scripts/tests/test_service_workflows.cjs
```

The first command executes the Python infrastructure tests. The second executes the Node.js workflow tests.

### E. Frontend — React / TypeScript

The following commands work on both Windows and Linux.

First, navigate to the frontend:

```bash
cd Frontend
```

| Test category | Command |
|---|---|
| ESLint | `npm run lint` |
| TypeScript checking | `npm run typecheck` |
| All Vitest tests | `npm run test` |
| Unit tests | `npm run test:unit` |
| Functional tests | `npm run test:functional` |
| Integration tests | `npm run test:integration` |
| Vitest with coverage | `npm run test:coverage` |
| Production build | `npm run build` |
| Playwright E2E | `npm run test:e2e` |

The automatic runner executes:

- ESLint
- TypeScript checking
- Vitest with coverage
- Production build
- Playwright E2E

The separate unit, functional and integration commands are useful when working on a specific feature.

Return to the repository root afterward:

```bash
cd ..
```

### F. Mapping Converter — Python

The `Mapping_Converter` service does not currently contain a `tests/` directory.

Once tests are added, the automatic runner will include its pytest and Ruff checks.

**Windows:**

```powershell
cd Mapping_Converter

python -m pytest -q
python -m ruff check .

cd ..
```

**Linux:**

```bash
cd Mapping_Converter

python3 -m pytest -q
python3 -m ruff check .

cd ..
```

These commands are intended for future use once the service contains tests and its required Python dependencies.

---

## 3. First-Time Setup

Before running the tests, ensure the following tools are installed:

- Python with the project's dependencies
- Java JDK 21
- Node.js and npm
- Docker (only for tests or workflows that require containers)

The Java projects include Maven wrappers, so installing Maven separately is normally unnecessary.

### Python Dependencies

From `Mapping_Proposal/`:

**Windows:**

```powershell
python -m pip install -r requirements.txt
```

**Linux:**

```bash
python3 -m pip install -r requirements.txt
```

If Ruff is not installed:

```bash
python -m pip install ruff
```

On Linux, use `python3` instead of `python` where necessary.

### Frontend Dependencies

From `Frontend/`, on either operating system:

```bash
npm ci
```

### Playwright Browser Installation

From `Frontend/`:

```bash
npx playwright install chromium
```

On Linux, additional system dependencies may be necessary:

```bash
npx playwright install --with-deps chromium
```

The Playwright configuration automatically starts the required frontend test server, so starting the application manually is normally unnecessary.

---

## 4. Troubleshooting

### Playwright Tests Fail

Navigate to `Frontend/` and execute:

```bash
npx playwright install chromium
npm run test:e2e
```

To inspect the test report:

```bash
npx playwright show-report
```

A Playwright failure does not necessarily mean Chromium is missing. Check the actual error output.

### Python Dependencies Are Missing

If Python reports `No module named pytest` or `No module named ruff`, install the missing dependencies in the active Python environment.

### Maven Tests Fail

Verify the installed Java version:

```bash
java -version
```

Ensure JDK 21 is available and the Maven wrapper can download its dependencies.

### Frontend Tests Fail

From `Frontend/`:

```bash
npm ci
```

Also verify that your Node.js version meets the project's requirements.

### Running Tests Takes Too Long

Skip browser-based tests during development:

**Windows:**

```powershell
.\Scripts\run-tests.cmd --skip-e2e
```

**Linux:**

```bash
bash Scripts/run-tests.sh --skip-e2e
```

Skipping E2E tests does not mean they passed.

---

## 5. Recommended Workflow

During development, run the tests for the component you modified.

Before opening or merging a Pull Request, run the complete project test suite.

**Windows:**

```powershell
.\Scripts\run-tests.cmd
```

**Linux:**

```bash
bash Scripts/run-tests.sh
```

Verify that all checks pass and review the GitHub Actions CI results.

The local test runner does not replace Kubernetes deployment verification or integration testing against external services.
