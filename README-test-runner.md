
# Essers_Mapping — Running the Tests

This guide explains how to run the entire test suite or test individual components on **Windows (PowerShell)** and **Linux**.

The main test runners are located in `Scripts/`. This README is at the repository root.

Unless otherwise specified, commands are executed from the repository root (`Essers_Mapping/`).

## 1. Run All Tests

The test runner executes the configured automated tests and local quality checks across the project. SonarQube for IDE remains a manual review.

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

If any automated check fails, the runner exits with code `1`. The IDE review is shown as **MANUAL** and is not automatically certified.

### Useful Options

| Purpose | Windows | Linux |
|---|---|---|
| Run everything | `.\Scripts\run-tests.cmd` | `bash Scripts/run-tests.sh` |
| Quality checks only | `python Scripts/run-tests.py --only-quality` | `python3 Scripts/run-tests.py --only-quality` |
| Skip quality checks | `python Scripts/run-tests.py --skip-quality` | `python3 Scripts/run-tests.py --skip-quality` |
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

### G. Local Code Quality — Individual Checks

Run these commands **from the repository root** (`Essers_Mapping/`). They match the commands used by `Scripts/run-tests.py`, so you can investigate one check without running the entire suite. On Windows, keep the `Scripts/` prefix when running from the root; if you have already entered `Scripts/`, use `python run-tests.py` instead.

**Semgrep — static analysis** (Windows / Linux):

```powershell
semgrep scan --config p/default --error --metrics off --exclude .git --exclude node_modules --exclude .venv --exclude dist --exclude target .
```

This uses the same ruleset and excludes as the automated runner. `--error` returns exit code `1` when findings are present. The ruleset may require internet access on the first scan.

**Gitleaks — current files (same as the runner)** (Windows / Linux):

```powershell
gitleaks dir . --redact --no-banner
```

This scans files currently present on disk, potentially including **untracked and Git-ignored files** (such as local `.env` files or `data/`). It can fail even when Git history is clean. `--redact` avoids printing full detected secrets; do not share actual secret values.

**Gitleaks — Git history (additional, separate check)** (Windows / Linux):

```powershell
gitleaks git . --redact
```

This scans commits and is **not** the check currently executed by `run-tests.py`. A clean Git-history result does not imply that local files are clean, or vice versa.

**jscpd — duplicate code** (Windows PowerShell):

```powershell
.\Scripts\node_modules\.bin\jscpd.cmd . --min-lines 10 --min-tokens 70 --threshold 10 --gitignore --ignore '**/node_modules/**,**/.git/**,**/.venv/**,**/target/**,**/dist/**,**/coverage/**' --reporters console
```

**jscpd — duplicate code** (Linux/macOS):

```bash
./Scripts/node_modules/.bin/jscpd . --min-lines 10 --min-tokens 70 --threshold 10 --gitignore --ignore '**/node_modules/**,**/.git/**,**/.venv/**,**/target/**,**/dist/**,**/coverage/**' --reporters console
```

The `10` in `--threshold 10` is the team's configured **10% duplication threshold**. Exceeding it causes exit code `1`; this is a quality finding, not an installation failure. Run `npm install` (or `npm ci` after committing the lockfile) **inside `Scripts/`** first.

**SonarQube for IDE (formerly SonarLint) — manual review:** Install the **SonarQube for IDE** extension in VS Code or IntelliJ, open the repository, and examine relevant findings in the IDE (in VS Code, use **View → Problems**, `Ctrl+Shift+M`). Resolve or document findings before merging. There is no equivalent CLI command in this runner; the repository's SonarQube GitHub Action is a separate CI check.

**All automated quality checks together** (from the repository root):

```powershell
python Scripts/run-tests.py --only-quality
```

A summary of `FAIL` with exit code `1` usually means the tool **found something** (Semgrep findings, Gitleaks secrets or jscpd duplication above the configured limit). Look at the detailed output for the relevant check above the summary to identify the actual cause.

---

## 3. First-Time Setup

All commands below assume you start at the **repository root**. The tools in different languages are installed using their own package managers; a Python `requirements.txt` cannot install Node.js applications, Java, IDE extensions or standalone executables.

### Required Tools

Install these tools before attempting the full suite:

| Tool | Needed for | Verify installation |
|---|---|---|
| Python + pip | Python tests, Ruff and Semgrep | `python --version` / `python -m pip --version` |
| Java JDK **21** | Java services (Maven wrappers supplied) | `java -version` |
| Node.js + npm | Frontend and jscpd | `node --version` / `npm --version` |
| Git | Repository history scan and development | `git --version` |
| Docker | Only tests/workflows that use containers | `docker --version` |

You generally **do not need to install Maven** because `Version_Control/` and `Runtime/` include Maven wrappers (`mvnw` / `mvnw.cmd`). Install Node.js, Java 21, Python and Git using their official installers or your platform's package manager. Docker is only required for the parts of the project that use it.

### A. Python Environment and Dependencies

Using a virtual environment keeps application and quality-check dependencies isolated. If you already have an activated `(.venv)`, **do not recreate it**; just run the installation commands.

**Windows (PowerShell, from repository root):**

```powershell
# Only when creating a new environment:
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies into the active environment:
python -m pip install --upgrade pip
python -m pip install -r Mapping_Proposal/requirements.txt -r Mapping_Converter/requirements.txt -r Scripts/requirements-quality.txt ruff
```

**Linux/macOS (from repository root):**

```bash
# Only when creating a new environment:
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r Mapping_Proposal/requirements.txt -r Mapping_Converter/requirements.txt -r Scripts/requirements-quality.txt ruff
```

`Mapping_Proposal/requirements.txt` installs its Python test/application dependencies (including pytest). `Mapping_Converter/requirements.txt` supplies converter dependencies. `Scripts/requirements-quality.txt` installs **Semgrep**. **Ruff** is installed separately because it is used by the test runner but is not listed in these manifests. Keep the virtual environment activated when running `python Scripts/run-tests.py`.

Verify:

```powershell
python -m pytest --version
python -m ruff --version
semgrep --version
```

If `semgrep` isn't recognized but the package was installed, verify the active environment with `python -m pip show semgrep`; the test runner searches the active Python environment for it.

### B. Node.js Dependencies — Frontend and jscpd

These are **two independent npm projects**, each with its own `package.json` and `node_modules/` folder.

**From the repository root (Windows PowerShell):**

```powershell
cd Scripts
npm install
cd ..

cd Frontend
npm ci
cd ..
```

The commands above also work in a Linux/macOS shell. For subsequent clean installations, use `npm ci` **inside `Scripts/`** as well, once `Scripts/package-lock.json` is present and committed. Commit `Scripts/package.json` and `Scripts/package-lock.json`, but **do not commit `node_modules/`**.

Verify **jscpd** from the repository root:

```powershell
# Windows: should output True
Test-Path .\Scripts\node_modules\.bin\jscpd.cmd
```

```bash
# Linux/macOS: should print a version
./Scripts/node_modules/.bin/jscpd --version
```

**Important:** Do **not** run `npm install --prefix Scripts` for this repository. On the tested Windows setup it tried to find `Essers_Mapping/package.json` (which does not exist) and could create an accidental nested `Scripts/Scripts/` directory. Enter `Scripts/` and run `npm install` directly.

### C. Gitleaks — Standalone Executable

Gitleaks is **not a Python package**, so it cannot be installed via `requirements-quality.txt`. On Windows, use:

```powershell
winget install --id Gitleaks.Gitleaks -e
```

Then open a **new terminal** (or restart VS Code if needed) and verify:

```powershell
gitleaks version
```

**Windows troubleshooting — installed by Winget but still `not recognized`:** On some installations Winget downloads `gitleaks.exe` but fails to create its alias in `Microsoft\WinGet\Links`. Locate the executable and make its directory available in the current terminal:

```powershell
$gitleaksExe = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter gitleaks.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
$gitleaksDir = Split-Path $gitleaksExe -Parent
$env:Path += ";$gitleaksDir"
gitleaks version
```

If this works, make it permanent in your **user PATH** (no administrator access required):

```powershell
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $gitleaksDir) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $gitleaksDir), 'User')
}
```

Restart your terminal/VS Code afterward. If the first command finds nothing, check the Winget installation or download Gitleaks from its official GitHub releases. On Linux/macOS, install the platform-specific Gitleaks executable through the official releases or an appropriate package manager, ensure it is on `PATH`, and verify with `gitleaks version`.

### D. SonarQube for IDE — Manual Installation

In VS Code, open the Extensions view (`Ctrl+Shift+X`), search for **SonarQube for IDE** (formerly SonarLint), and install it. For IntelliJ, install the corresponding plugin. Open the repository and review the IDE's findings before merging. The `run-tests.py` script marks this check **MANUAL**, not PASS.

The project's `.github/workflows/sonarqube.yml` is a separate CI workflow and does not replace the required local IDE review.

### E. Playwright Browser Installation

After installing the frontend dependencies, install Chromium for Playwright from `Frontend/`:

```powershell
cd Frontend
npx playwright install chromium
cd ..
```

On Linux, system packages may also be required. Run from `Frontend/`:

```bash
npx playwright install --with-deps chromium
```

The Playwright configuration starts its test server automatically; manually starting the frontend is normally unnecessary.

### F. Confirm the Quality Tools

From the repository root on Windows:

```powershell
semgrep --version
gitleaks version
Test-Path .\Scripts\node_modules\.bin\jscpd.cmd
python Scripts/run-tests.py --only-quality
```

Missing tools are reported as **FAIL** rather than silently skipped. Findings from successfully installed tools also produce FAIL, so review the detailed scan output instead of treating every `Exit code 1` as an installation problem.

#### What the Quality Checks Scan

| Tool | Scope in current runner | Typical failing condition |
|---|---|---|
| Semgrep | Repository static security/code patterns (`p/default`, metrics off) | Rules report findings (`--error`) |
| Gitleaks | Local directory, including uncommitted files | Possible secret in local files; **does not scan Git history** |
| jscpd | Code duplication, excluding dependencies and build output | More than 10% duplication under the configured thresholds |
| SonarQube for IDE | Code inspection in the developer's IDE | Manual review, never automatically marked PASS |

The 10% duplication limit is a team policy used by this script, not a universal standard. Maven `verify` runs integration tests only if they have been configured in the relevant Maven lifecycle.

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

### Semgrep: Cannot Create Auto Config When Metrics Are Off

This happened with an older version of `Scripts/run-tests.py` that combined `--config auto` with `--metrics off`. The runner now uses `--config p/default` instead. Replace your runner with the updated script and retry.

### Local Quality Tool Not Found

Use the tool-specific instructions in **First-Time Setup**. In particular:

- **Gitleaks:** Winget may install `gitleaks.exe` without an alias. Use **Section 3C** to locate it and update your PATH.
- **jscpd:** Run `npm install` **inside `Scripts/`** and verify that `Scripts/node_modules/.bin/jscpd.cmd` exists (Windows).
- **Semgrep:** Install `Scripts/requirements-quality.txt` into the same active Python environment that runs `Scripts/run-tests.py`.

### Gitleaks Git History Passes but the Test Runner Fails

The runner uses `gitleaks dir . --redact --no-banner` (local files), while `gitleaks git . --redact` checks Git commit history. Both can produce different results. Inspect the relevant findings and **avoid staging local secrets or example data indiscriminately**. A new untracked `data/` folder should be reviewed before any `git add` or commit.

### Quality Check Exits With Code 1

This frequently indicates a *successful scan with reported findings*, not a broken installation. Semgrep fails when rules match (`--error`); jscpd fails above the configured duplication threshold; Gitleaks fails if it finds suspected secrets. Consult the detailed scan output, investigate false positives, and fix actual issues before merging.
