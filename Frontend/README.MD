# Essers Mapping Engine - Frontend

Modern React single-page application (SPA) for the **H.Essers AI Mapping Engine**. This dashboard allows logistics and interface analysts to upload customer interface specifications (XML), trigger the AI mapping pipeline, and navigate mapping and version control workflows.

---

## 📋 Table of Contents

- [Tech Stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Getting Started & Installation](#-getting-started--installation)
- [Environment Variables](#-environment-variables)
- [Building & Running for Manual Testing](#-building--running-for-manual-testing)
- [Automated Testing & Quality Checks](#-automated-testing--quality-checks)
- [Version Bump Checklist (e.g. `0.0.0` → `0.1.0`)](#-version-bump-checklist-eg-000--010)
- [Project Structure](#-project-structure)
- [Architecture & Deployment Context](#-architecture--deployment-context)

---

## 🛠 Tech Stack

- **Framework**: [React 19](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- **Bundler & Dev Server**: [Vite 8](https://vite.dev/)
- **Styling**: [Tailwind CSS v4](https://tailwindcss.com/)
- **Routing**: [React Router v7](https://reactrouter.com/) (Browser router with SPA deep linking)
- **Unit & Integration Testing**: [Vitest 3](https://vitest.dev/) + [React Testing Library](https://testing-library.com/) + JSDOM
- **End-to-End (E2E) Testing**: [Playwright](https://playwright.dev/)
- **Linting & Code Quality**: [ESLint 10](https://eslint.org/) + typescript-eslint

---

## ⚙️ Prerequisites

- **Node.js**: `v20.x` or later (LTS recommended)
- **npm**: `v10.x` or later
- **Playwright Chromium**: required for running E2E tests locally (see installation below)
- *(Optional)* **Backend API**: The Mapping Proposal API running on `http://localhost:8000` (for end-to-end integration with live backend services)

---

## 🚀 Getting Started & Installation

1. **Clone the repository and navigate to the frontend directory**:
   ```bash
   cd Frontend
   ```

2. **Install project dependencies**:
   ```bash
   npm install
   ```

3. **Install Playwright browsers** (required once for E2E tests):
   ```bash
   npx playwright install chromium
   ```

---

## 🌐 Environment Variables

Environment variables can be configured using a `.env` file in the `Frontend/` root:

| Variable | Default Value | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Base URL for the Mapping Proposal API backend |
| `PLAYWRIGHT_BASE_URL` | `http://127.0.0.1:4173` | Target URL used by Playwright E2E tests |
| `PLAYWRIGHT_SKIP_WEBSERVER` | _undefined_ | If set to `1` or `true`, Playwright skips launching the preview webserver |

Example `.env`:
```env
VITE_API_URL=http://localhost:8000
```

---

## 🖥 Building & Running for Manual Testing

### 1. Development Mode (with Hot Module Replacement)
Use this mode when actively developing features:
```bash
npm run dev
```
- Opens a local development server at `http://localhost:5173`.
- Changes to source files are immediately reflected in the browser without losing component state.

---

### 2. Production Build
Compile and bundle the TypeScript & React application into static assets:
```bash
npm run build
```
- Output directory: `./dist`
- Generates minified JavaScript chunks, extracted CSS, and asset bundles.

---

### 3. Production Preview (Manual Testing in Production Mode)
Simulate the production environment locally by serving the compiled `./dist` directory:
```bash
# 1. First ensure you have a fresh build
npm run build

# 2. Start the local preview server
npm run preview
```
- Serves the application at `http://localhost:4173`.
- Allows you to test asset loading, minification behavior, routing fallbacks, and real performance before deploying.

---

### 4. Manual Testing Checklist
When verifying changes manually in the browser:

1. **Navigation & Sidebar**:
   - Check that the H.Essers branding, logo, and active menu indicators render correctly.
   - Click between **Home** (`/`) and **Version Control** (`/version-control`) to verify client-side routing.
2. **Interface Upload Flow (`/`)**:
   - **Validation - Empty Customer**: Try clicking **Uploaden** without entering a customer name → check that an alert is shown.
   - **Validation - No File**: Enter a customer name but select no file → verify file requirement warning.
   - **Validation - Invalid File Type**: Attempt to upload a non-XML file (e.g. `.pdf` or `.png`) → verify it is rejected with an error message.
   - **Valid File Upload**: Select one or more `.xml` files, enter a customer name, and click **Uploaden**:
     - *With backend running*: verify successful upload confirmation banner (`Interface succesvol geüpload voor <klant>`).
     - *Without backend running*: verify graceful error display indicating the server is unreachable.
3. **Deep Link / Direct URL Refresh**:
   - Navigate to `/version-control` or any nested path and press browser refresh (`F5` / `Ctrl+R`) to ensure no 404 error occurs.

---

## 🧪 Automated Testing & Quality Checks

The project includes unit, functional, integration, coverage, and end-to-end tests.

### Summary of Test Commands

| Command | Tool | Purpose |
|---|---|---|
| `npm run lint` | ESLint | Checks code style, TypeScript safety, and React best practices |
| `npm test` | Vitest | Runs all unit, functional, and integration tests once |
| `npm run test:unit` | Vitest | Runs component unit tests (`src/__tests__/unit/`) |
| `npm run test:functional` | Vitest | Runs functional component tests (`src/__tests__/functional/`) |
| `npm run test:integration` | Vitest | Runs router & page integration tests (`src/__tests__/integration/`) |
| `npm run test:coverage` | Vitest + v8 | Generates code coverage report in terminal and `./coverage` |
| `npm run test:e2e` | Playwright | Runs end-to-end tests in headless Chromium |

---

### Running the Vitest Suites
Vitest runs headless tests in a JSDOM environment with testing-library:

```bash
# Run all Vitest tests
npm test

# Run tests in watch mode (reruns on file changes)
npx vitest

# Run only unit tests
npm run test:unit

# Run only functional tests
npm run test:functional

# Run only integration tests
npm run test:integration
```

---

### Running Test Coverage
To generate a comprehensive test coverage report:
```bash
npm run test:coverage
```
- Displays tabular coverage metrics in your terminal (Statements, Branches, Functions, Lines).
- Detailed HTML reports are generated in `./coverage/index.html` (open in your browser to inspect line-by-line coverage).
- Machine-readable XML reports are written to `./test-results/vitest-junit.xml`.

---

### Running End-to-End (E2E) Tests with Playwright
Playwright tests verify browser interactions, routing, and upload flows in real Chromium:

```bash
# 1. Ensure the production bundle is up to date
npm run build

# 2. Run E2E tests headlessly
npm run test:e2e
```

**Interactive Playwright Modes:**
```bash
# Run with interactive UI mode (debugger, time-travel, DOM snapshots)
npx playwright test --ui

# Run with visible browser window (headed mode)
npx playwright test --headed

# View the detailed HTML report from the last test run
npx playwright show-report
```

> **Note**: Playwright automatically launches `npm run preview` during test runs, and mocks backend API calls (`page.route('**/upload')`) so E2E tests run reliably without an external API dependency.

---

### Full Pre-Commit / Pre-PR Verification One-Liner
Before opening a Pull Request or committing significant changes, run the full verification pipeline:
```bash
npm run lint && npm run test:coverage && npm run build && npm run test:e2e
```

---

## 🏷 Version Bump Checklist (e.g. `0.0.0` → `0.1.0`)

Follow this step-by-step checklist whenever releasing a new version or bumping the frontend version:

### 1. Branch Preparation
- [ ] Confirm you are on your working feature branch (e.g. `Feature/<feature-name>`).
- [ ] Pull and sync with the latest `Development` branch to avoid merge conflicts:
  ```bash
  git fetch origin
  git merge origin/Development
  ```

### 2. Determine the Semantic Version (SemVer)
- [ ] **PATCH** (`0.0.0` → `0.0.1`): Backwards-compatible bug fixes or minor chore adjustments.
- [ ] **MINOR** (`0.0.0` → `0.1.0`): Backwards-compatible new features (e.g. new UI pages, file upload card, new service integrations).
- [ ] **MAJOR** (`0.1.0` → `1.0.0`): Breaking changes, major redesigns, or first production-ready release.

### 3. Update Version in Files
- [ ] Update `package.json` and sync `package-lock.json`:
  ```bash
  # Using npm command:
  npm version 0.1.0 --no-git-tag-version

  # Or manually edit "version": "0.1.0" in package.json, then run:
  npm install --package-lock-only
  ```
- [ ] Verify `package.json` and `package-lock.json` reflect the new version:
  ```bash
  grep '"version":' package.json package-lock.json
  ```
- [ ] If applicable, update any Kubernetes deployment image tags or environment references (e.g. `Kubernetes/base/preparation/frontend.yaml`).

### 4. Run the Full Test Suite
- [ ] Lint check passes:
  ```bash
  npm run lint
  ```
- [ ] Unit, functional, and integration tests pass with coverage:
  ```bash
  npm run test:coverage
  ```
- [ ] Production build succeeds without errors:
  ```bash
  npm run build
  ```
- [ ] E2E tests pass completely:
  ```bash
  npm run test:e2e
  ```

### 5. Commit According to GitFlow Rules
- [ ] Per project guidelines in `GITFLOW.md`, commit messages must be **multiline** using the **50/72 rule** and conventional commit syntax:
  ```bash
  git add package.json package-lock.json
  git commit
  ```
  *Example commit message:*
  ```text
  chore(release): bump frontend version to 0.1.0

  Update frontend package version and lockfile to 0.1.0 following
  the completion of the customer interface upload dashboard feature.

  - Bump version in package.json and package-lock.json
  - Verify all unit, functional, integration, and E2E tests pass
  ```

### 6. Git Tagging (Release Steps)
- [ ] When ready to release or merge to `Testing` / `main`:
  ```bash
  git tag -a frontend-v0.1.0 -m "Release frontend v0.1.0"
  git push origin frontend-v0.1.0
  ```

### 7. Pull Request
- [ ] Push your branch:
  ```bash
  git push -u origin Feature/<feature-name>
  ```
- [ ] Open a Pull Request targeting `Development` on GitHub.
- [ ] Ensure all CI checks pass and obtain review approval.

---

## 📁 Project Structure

```text
Frontend/
├── e2e/                             # Playwright End-to-End tests
│   ├── app.spec.js                  # Navigation, title, and SPA routing checks
│   └── upload.spec.js               # XML file upload flows (TC-48 & TC-60)
├── public/                          # Static assets copied directly to dist/
├── src/
│   ├── assets/                      # SVGs, icons, and H.Essers branding
│   ├── components/                  # Shared React UI components
│   │   ├── InterfaceUpload.tsx      # Customer file upload card with validation
│   │   └── Sidebar.tsx              # Application sidebar navigation
│   ├── pages/                       # Route view components
│   │   ├── Home.tsx                 # Dashboard home page
│   │   └── VersionControl.tsx       # Version control overview page
│   ├── router/
│   │   └── index.tsx                # React Router v7 configuration
│   ├── services/
│   │   └── uploadService.ts         # Mapping Proposal API client (POST /upload)
│   ├── test/
│   │   └── setup.js                 # Vitest & Jest-DOM global test setup
│   ├── __tests__/                   # Automated Vitest suites
│   │   ├── functional/              # Component behavior & user interaction tests
│   │   ├── integration/             # Router & page integration tests
│   │   └── unit/                    # Isolated component unit tests
│   ├── App.tsx                      # Root application layout with Sidebar & Outlet
│   ├── index.css                    # Tailwind CSS imports & global styles
│   └── main.tsx                     # Vite entry point
├── eslint.config.js                 # ESLint flat config
├── index.html                       # HTML document template
├── package.json                     # Scripts, dependencies, and versioning
├── playwright.config.js             # Playwright E2E configuration & webserver setup
├── tsconfig.json                    # TypeScript compiler options
└── vite.config.js                   # Vite & Vitest configuration
```

---

## 🏛 Architecture & Deployment Context

In production (Kubernetes `preparation` zone), the compiled frontend is packaged into an NGINX container:
- **Port 8080**: Serves the static single-page application (`dist/`).
- **SPA Routing**: Configured with `try_files $uri $uri/ /index.html` to allow direct access to deep links without 404 errors.
- **Reverse Proxy**: NGINX proxies `/api/*` endpoints to backend microservices:
  - `/api/converter/*` → `http://mapping-converter:8000/`
  - `/api/proposal/*` → `http://mapping-proposal:8000/`
  - `/api/version-control/*` → `http://version-control-backend:8080/`
- **Health Check**: Kubernetes liveness/readiness probes check `/healthz`.
