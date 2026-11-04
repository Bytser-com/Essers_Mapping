# GitHub Actions CI/CD Workflows (`Essers_Mapping/.github/workflows`)

## 1. Full-Stack CI & SonarQube Pipeline ([`ci-pipeline.yml`](./ci-pipeline.yml))

Runs automatically on **every Pull Request** and **Push** targeting:
- `main`
- `testing` / `Testing`
- `development` / `Development`

### Pipeline Architecture & Jobs

| Job | Runner | Responsibilities | Coverage / Report Output |
| :--- | :--- | :--- | :--- |
| **`discover`** (`Discover Stack & Services`) | `ubuntu-latest` | Dynamically discovers the React 19 Frontend, all Spring Boot 4 Maven backends (`pom.xml`), and all Python backend services (`Mapping_Converter`, `Mapping_Proposal`, `ai_tool`, etc.). | Dynamic job matrices |
| **`frontend-tests`** (`Frontend (React 19) - Lint, Unit, Functional & Integration`) | `ubuntu-latest` | Runs ESLint static analysis, **Unit Tests** (`npm run test:unit`), **Functional Tests** (`npm run test:functional`), **Integration Tests** (`npm run test:integration`), **V8 Code Coverage** (`npm run test:coverage`), and verifies the production Vite bundle (`npm run build`). | `Frontend/coverage/lcov.info`<br>`Frontend/test-results/vitest-junit.xml` |
| **`java-backends-tests`** (`Java Spring Boot 4 (...) - Unit, Integration, Functional & Coverage`) | `ubuntu-latest` | Parallel matrix over every Spring Boot 4 backend (`Runtime/Runtime`, and any future Java backend). Runs **Unit Tests** via Maven Surefire (`*Test.java`, `*Tests.java`, `*UnitTest.java`), **Integration & Functional Tests** via Maven Failsafe (`*IT.java`, `*IntegrationTest.java`, `*FunctionalTest.java`), and merges coverage via **JaCoCo**. | `<service>/target/site/jacoco/jacoco.xml`<br>`<service>/target/surefire-reports`<br>`<service>/target/failsafe-reports` |
| **`python-backends-tests`** (`Python Backend (...) - Lint, Unit, Functional, Integration & Coverage`) | `ubuntu-latest` | Parallel matrix over every Python backend (`Mapping_Converter`, `Mapping_Proposal`, etc.). Runs syntax/static checks (`compileall` + `ruff`) and executes **Unit, Functional, and Integration tests** with `pytest --cov`. | `<service>/coverage.xml`<br>`<service>/test-results/pytest-junit.xml` |
| **`e2e-tests`** (`End-to-End (E2E) - React 19, Nginx & Backend Smoke Tests`) | `ubuntu-latest` | Serves the production React 19 bundle inside **Nginx (`nginx:1.27-alpine` / `Frontend/Dockerfile`)**, verifies `/healthz`, `nginx -t`, SPA fallback routing, HTTP security headers, hidden dotfile blocking, and runs **Playwright Headless Chromium E2E tests** (`npx playwright test`). | `Frontend/playwright-report`<br>`Frontend/test-results/playwright-junit.xml` |
| **`sonarqube`** (`SonarQube - Code Coverage & Quality Gate`) | `ubuntu-latest` | Aggregates Frontend (`lcov.info`), Java (`jacoco.xml` + bytecode), and Python (`coverage.xml`) reports, executes the **SonarQube Scanner**, and enforces the **SonarQube Quality Gate** (`-Dsonar.qualitygate.wait=true`). | SonarQube Dashboard & PR Decoration |
| **`ci-quality-gate`** (`CI Quality Gate`) | `ubuntu-latest` | Final aggregator gate (`if: always()`) that verifies every test stage and SonarQube Quality Gate succeeded. Fails (`exit 1`) if any upstream job failed or was cancelled. | Required Status Check for PR Rulesets |

---

## 2. Required GitHub Secrets & Variables for SonarQube

Configure the following in **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

| Name | Type | Description |
| :--- | :--- | :--- |
| **`SONAR_TOKEN`** | Repository Secret | Authentication token generated in SonarCloud under *My Account $\rightarrow$ Security*. |
| **`SONAR_HOST_URL`** | Repository Secret or Variable | Base URL: `https://sonarcloud.io` |
| **`SONAR_PROJECT_KEY`** | Optional Variable | Defaults to `Bytser-com_Essers_Mapping` (matching [`sonar-project.properties`](../../sonar-project.properties)). |
| **`SONAR_ORGANIZATION`** | Optional Variable | Defaults to `bytser-com`. |

---

## 3. Blocking Pull Request Merges (GitHub Repository Ruleset Setup)

To block Pull Requests from being merged into `main`, `testing`, or `development` unless the entire CI pipeline and SonarQube Quality Gate succeed:

1. Go to **Repository Settings $\rightarrow$ Rules $\rightarrow$ Rulesets $\rightarrow$ New branch ruleset**.
2. Set **Target branches** to include `main`, `testing`, `Testing`, `development`, and `Development`.
3. Enable **Require a pull request before merging**.
4. Enable **Require status checks to pass** and add:
   - **`CI Quality Gate`** *(single aggregated gate check that only succeeds when all Frontend, Java, Python, E2E, and SonarQube jobs pass)*
5. *(Optional)* Enable **Require branches to be up to date before merging**.

---

## 4. End-to-End Infrastructure & Cluster Pipeline ([`infra-pipeline.yml`](./infra-pipeline.yml))

Orchestrates the multi-tier Infrastructure-as-Code (IaC) deployment to ensure determinism, zero race conditions, and complete idempotency.

### Pipeline Execution Flow

```text
Push / PR to main or Testing
              │
              ▼
┌──────────────────────────────────────────────┐
│ 1. Terraform (terraform-infra.yml)           │
│    - PR:   plan (fmt, init, validate, plan)  │
│    - Push: plan + apply (if changes exist)   │
└──────────────────────┬───────────────────────┘
                       │ (Success / No Changes)
                       ▼
┌──────────────────────────────────────────────┐
│ 2. Ansible (ansible-infra.yml)               │
│    - PR:   syntax-check, inventory & lint    │
│    - Push: syntax & lint + live configure    │
└──────────────────────┬───────────────────────┘
                       │ (Success)
                       ▼
┌──────────────────────────────────────────────┐
│ 3. Kubernetes (kubernetes-deploy.yml)        │
│    - PR:   syntax & Kustomize build checks   │
│    - Push: syntax & live overlay CD deploy   │
└──────────────────────────────────────────────┘
```

### Best Practices Implemented

1. **Single Entry Point (`infra-pipeline.yml`)**:
   - Monitors `Infra/**`, `Kubernetes/**`, and workflow directories.
   - Prevents parallel trigger collisions where Ansible or Kubernetes would start before Terraform finishes creating or updating VMs.
2. **Modular Reusable Workflows (`workflow_call`)**:
   - [`terraform-infra.yml`](./terraform-infra.yml), [`ansible-infra.yml`](./ansible-infra.yml), and [`kubernetes-deploy.yml`](./kubernetes-deploy.yml) serve as dedicated, testable reusable workflows.
   - Each retains direct `workflow_dispatch` support for ad-hoc administrative tasks (e.g. Terraform destroy, Ansible `--limit` / `--tags`, or Kubernetes rollout restart).
3. **Strict Concurrency Protection**:
   - Concurrency group `infra-cluster-pipeline-${{ github.base_ref || github.ref_name }}` ensures only one active run per environment (`Testing` or `Production`), queuing subsequent pushes without state corruption.
4. **Graceful Zero-Drift Handling**:
   - If Terraform detects no changes (`has_changes=false`), it cleanly passes execution to Ansible and Kubernetes so code changes in playbooks or Kubernetes overlays are always deployed without manual re-runs.
