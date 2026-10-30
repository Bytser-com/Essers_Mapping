# GitHub Actions workflows

## Service CI

Each application service has its own workflow:

| Workflow | Checks | Artifacts |
| --- | --- | --- |
| [Frontend CI](./frontend-ci.yml) | ESLint, TypeScript, Vitest with V8 coverage, production build, Playwright E2E, Docker build and Nginx health/SPA smoke tests | `frontend-test-reports`, `frontend-dist` |
| [Runtime CI](./runtime-ci.yml) | Java 21, Surefire/Failsafe tests, JaCoCo coverage, JAR packaging, Docker build and HTTP health smoke test | `runtime-test-reports`, `runtime-jar` |
| [Mapping Proposal CI](./mapping-proposal-ci.yml) | Python 3.12, Ruff lint, pytest unit/integration/functional tests with branch coverage | `mapping-proposal-test-reports` |
| [Mapping Converter CI](./mapping-converter-ci.yml) | Python 3.12, Ruff lint, pytest unit/integration/functional tests with branch coverage | `mapping-converter-test-reports` |

Service workflows run on pull requests and pushes to `main`, `Testing`, and
`Development`. They can also be started manually from Actions.
They use GitHub-hosted Ubuntu runners and need no repository secrets.

The shared [service change action](../actions/service-changes/action.yml) checks
for changes in the service directory, its workflow, the shared action,
`.gitattributes`, and any shared service dependencies. Unrelated changes skip the expensive checks, while each workflow
still publishes its final status. Manual runs always execute all service checks.
New branches or unavailable comparison commits also execute all checks. Pull
requests compare the target commit with GitHub's checked-out merge commit;
pushes compare the previous commit with the new head.

Test reports are uploaded even when a check fails, if any were generated. Reports
are retained for 14 days; successful build artifacts are retained for 7 days.
Frontend browser tests use Vite preview to serve the production build. A separate
container smoke test checks Nginx health and SPA fallback. No CI test deploys to
the Kubernetes environment.

### Future Python services

`Mapping_Proposal` and `Mapping_Converter` currently contain only empty READMEs.
Their workflows use [shared Python CI](./python-service-ci.yml). Placeholder
directories report that checks are deferred and skip dependency installation,
linting and tests. They do not claim that Python tests passed.

To activate a service, add `requirements.txt` or an installable `pyproject.toml`,
plus automated tests under `tests/` (for example `tests/unit/`,
`tests/integration/`, and `tests/functional/`). CI installs the service's
dependencies and the [CI tools](../requirements/python-ci.txt); it also installs
`requirements-dev.txt` when present. Pin application dependencies in the service
manifest. The `.github/requirements/` directory holds shared CI dependencies:
Ruff checks Python code, pytest runs tests, and pytest-cov generates coverage.
These tools are installed only for Python CI, separate from application runtime
dependencies. Changes to the shared Python workflow or CI tools check both services.

Once Python code or a tests directory exists, a missing manifest fails CI. A
manifest without `tests/` also fails, and pytest fails if it collects no tests.
Test fixtures must be self-contained; add external dependencies such as SFTP as
CI service containers when those integrations are implemented.

To activate Python CD, also add a service `Dockerfile` and `.dockerignore` that
exclude credentials, local caches and test output. The container must run without
root privileges, accept a read-only root filesystem with writable `/tmp`, listen
on port 8000 and return HTTP 200 at `/health`. CI validates the image whenever a
Dockerfile is present; CD requires it. Placeholder services publish no image.

The architecture's Version Control API has no implementation directory yet.

### Required pull request checks

In repository Settings > Rules > Rulesets, require these checks on the protected
branches after the workflows have run once:

- `Frontend CI Gate`
- `Runtime CI Gate`
- `Mapping Proposal CI Gate`
- `Mapping Converter CI Gate`

Replace any requirement for the deleted pipeline's `CI Quality Gate`.
The new gates fail if change detection or required service checks fail or are
cancelled; they pass when a service is unaffected or is an unimplemented Python
placeholder. Do not add workflow-level
`paths` filters to these workflows: a filtered-out required workflow can leave a
pull request waiting for a status indefinitely.

Coverage reports are generated and uploaded for implemented services. Service
workflows need no Sonar secrets and do not impose a separate coverage percentage.
The SonarQube workflow enforces the quality gate configured in the hosted project.

### Hosted SonarQube and local feature work

[SonarQube](./sonarqube.yml) runs one combined analysis after each push to
`Development`, including a merged feature PR. It can also be started manually
with `Development` selected. It does not scan PRs or release branches.

The shared project key defaults to `Bytser-com_Essers_Mapping`; organization
defaults to `bytser-com`. Repository variables `SONAR_HOST_URL`,
`SONAR_PROJECT_KEY`, and optional `SONAR_ORGANIZATION` override these settings.
The repository secret `SONAR_TOKEN` is required. Configure `Development` as the
project's main branch in SonarQube Cloud and disable automatic analysis when
using this CI-based analysis.

The [Free plan](https://docs.sonarsource.com/sonarqube-cloud/administering-sonarcloud/managing-subscription/subscription-plans)
supports the main-branch setup within its private-code and user limits. This
repository already uses one shared project, so independent service scans must
not publish partial results to that same key.

The scan generates a complete coverage snapshot by rerunning the coverage tests
for every implemented service at the same commit, including unchanged services.
It imports Vitest LCOV, merged JaCoCo XML and pytest coverage XML using
[sonar-project.properties](../../sonar-project.properties). Python dependencies
are isolated per service; placeholders defer coverage. Service linting and
Playwright checks remain in the individual service workflows. Combined reports
are uploaded as `sonarqube-reports` for 14 days.

Use the free [SonarQube for IDE](https://www.sonarsource.com/products/sonarqube/ide/)
extension (formerly SonarLint) for local feature-branch analysis, alongside the
local test and coverage commands below. It can align rules with SonarQube Cloud
using Connected Mode. The extension does not replace test coverage collection.
A local CLI scan that publishes to Cloud is still subject to Cloud branch limits.

`SonarQube Quality Gate` is a post-merge check on `Development`; do not require
it as a PR status check. The four service CI gates above still protect PRs.

### Run the same checks locally

Frontend (Node.js 24):

```bash
cd Frontend
npm ci
npm run lint
npm run typecheck
npm run test:coverage
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Runtime (JDK 21 and Maven 3.9):

```bash
cd Runtime
mvn --batch-mode --no-transfer-progress clean verify
```

Use installed Maven until `Runtime/.mvn/wrapper/maven-wrapper.properties` is
restored; the checked-in wrapper scripts cannot run without that file.

Python (Python 3.12, from either service directory after activation):

```bash
python -m pip install -r ../.github/requirements/python-ci.txt
# Use requirements.txt, or `python -m pip install .` for pyproject.toml.
python -m pip install -r requirements.txt
# Install requirements-dev.txt as well, when present.
python -m pip check
python -m ruff check .
python -m pytest tests -ra --junitxml=test-results/pytest-junit.xml --cov=. --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-report=html:coverage
```

## Infrastructure and deployment

### Separate service CD workflows

CI and CD are separate files; the branch for this work is `Feature/service-ci-cd`.

| CD workflow | Successful source CI | GHCR image suffix / Deployment |
| --- | --- | --- |
| [Frontend CD](./frontend-cd.yml) | `Frontend CI` | `frontend` |
| [Runtime CD](./runtime-cd.yml) | `Runtime CI` | `runtime-backend` |
| [Mapping Proposal CD](./mapping-proposal-cd.yml) | `Mapping Proposal CI` | `mapping-proposal` |
| [Mapping Converter CD](./mapping-converter-cd.yml) | `Mapping Converter CI` | `mapping-converter` |

The workflows share [service-cd.yml](./service-cd.yml). A successful **push** CI
run on `Testing` or `main` triggers CD via `workflow_run`. PR and fork runs never
deploy. `Development` keeps CI and its combined SonarQube analysis. Manual CD
requires a successful push CI run for the current revision of `Testing` or `main`.
Keep CD deployment checks out of the required PR checks; they run after pushes.

GitHub only starts `workflow_run` workflows after their definitions exist on the
repository's default branch. Merge these workflow definitions there before
expecting automatic CD from `Testing`.

CD verifies the workflow/repository/branch and current SHA, then downloads the
build artifact from that exact CI run. Frontend packages CI's `dist/` and Runtime
packages CI's JAR. Python images build from the tested source revision. Container
startup and HTTP health checks pass before publication. Images use
`ghcr.io/<owner>/<repository>/<service>:sha-<full-commit>`; Kubernetes deploys the
returned immutable registry digest. Unchanged/placeholder services without
artifacts skip CD; expired artifacts require CI to be rerun.

`Testing` deploys to GitHub environment `Testing` / namespace
`essers-mapping-testing`; `main` deploys to `Production` /
`essers-mapping-production`. Environment protection rules apply before deploying.
The self-hosted runner must already have Kubernetes connectivity and the target
namespace/Deployment from infrastructure CD. Service CD changes only the chosen
Deployment and shared registry pull credentials, and waits for its rollout. A
second SHA check after environment approval rejects obsolete deployments.

### Registry credentials required for CD

Publishing uses the workflow's `GITHUB_TOKEN` with `packages: write`. Existing
packages must grant this repository Actions access. Kubernetes needs credentials
that remain valid after the workflow ends, so configure these in both target
environments or repository settings:

- **Secret `GHCR_TOKEN`**: a durable token with `read:packages` access to the
  service images (authorize organization SSO if applicable).
- **Variable `GHCR_USERNAME`**: the GitHub account that owns that token.

CD fails clearly if either is missing. It creates/updates `ghcr-pull-secret`
without writing credentials to the repository. Full Kubernetes CD uses the same
durable credentials; an expiring `GITHUB_TOKEN` is not used for cluster pulls.
Proxmox and SSH configuration keep the existing environment variable names.

### Infrastructure CD

- [Terraform infrastructure](./terraform-infra.yml): plan and apply infrastructure.
- [Ansible configuration](./ansible-infra.yml): check and configure VMs.
- [Kubernetes deployment](./kubernetes-deploy.yml): validate and deploy manifests.

Infrastructure workflows use functional filenames and retain their own triggers
and runners. They provision/configure the platform independently of service
image delivery. Local workflow calls and path filters use these same filenames.

Full Kubernetes reconciliation preserves digest-pinned images on Deployments
annotated `essers.io/image-managed-by=service-cd`, so it does not revert app
releases to bootstrap `latest`/`v1.0.0` manifest tags. Other manifest changes still
apply. Revert application code and let CI/CD deploy the new revision for a normal
rollback. To hand image selection back to manifests, remove that annotation
before reconciling. Kubernetes CD runs all tests in `Scripts/tests` via its
infrastructure preflight.

Runtime now includes an HTTP server and Actuator health endpoint on port 8080;
the former non-web startup stub could not satisfy the existing Kubernetes TCP
probes. Frontend uses unprivileged Nginx on port 8080; Kubernetes continues to
mount its cluster API reverse-proxy configuration over the image's standalone
SPA configuration.

Infrastructure workflows target `main` and `Testing`. GitHub environments are
`Production` and `Testing`; registered runner labels and inventory/overlay
directories use lowercase `production` and `testing`.

The existing order is Terraform plan/apply -> Ansible -> Kubernetes. Ansible
also runs when an authorized apply request produces a successful no-change plan;
failed/cancelled applies, destroy requests and PR plans do not deploy downstream.

Standalone Ansible and Kubernetes runs first use the read-only
[infrastructure check](../actions/check-infrastructure/action.yml). It queries
Proxmox with `PROXMOX_API_URL`, `PROXMOX_API_TOKEN`, and `NODE01_NAME`, and requires
all three VM IDs from `Infra/Setup/terraform.tfvars` to exist and be running.
Missing/stopped VMs fail with instructions to run Terraform/start the VMs;
network, authentication, permission and malformed-response errors fail as check
errors. They never trigger automatic infrastructure creation. The check accepts
self-signed TLS by default to match Terraform's `proxmox_api_insecure` default;
set its `insecure` input to `false` when that setting changes.

VM existence is a prerequisite, not proof of Terraform state consistency or a
working Kubernetes cluster. Ansible still checks SSH readiness and Kubernetes
still checks the API and node readiness. A runner must already exist to execute
the Terraform -> Ansible -> Kubernetes chain; it cannot bootstrap its own absence.

Terraform resolves its configuration inside the `plan` and `apply` jobs that
declare the GitHub environment. Each `TF_VAR_` suffix matches a declaration in
`Infra/Setup/variables.tf`. Testing provides the network, node, Proxmox API and
public-key variables; repository variables provide `CLOUD_IMAGE_URL` and
`CLOUD_IMAGE_CHECKSUM`. The provider uses SSH agent authentication, so no
`PROXMOX_SSH_PASSWORD` secret is required by this workflow.

Ansible receives `GH_REPO_URL` and `RUNNER_REGISTRATION_PAT` from the repository
settings for runner registration. `RUNNER_LABEL` is derived from the target
branch rather than requiring an additional GitHub variable.

Action configuration follows the official [checkout](https://github.com/actions/checkout),
[setup-node](https://github.com/actions/setup-node),
[setup-java](https://github.com/actions/setup-java), and
[upload-artifact](https://github.com/actions/upload-artifact) documentation.
See also GitHub's [configuration variable scope](https://docs.github.com/en/actions/reference/workflows-and-actions/variables#configuration-variable-precedence)
and [vars context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#vars-context)
documentation.
CD follows the official [GHCR publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
and [Docker Build](https://docs.docker.com/build/ci/github-actions/) documentation.
