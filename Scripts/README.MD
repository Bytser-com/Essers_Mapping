# Infrastructure preflight

`check-proxmox-vms.py` performs a read-only check that the three VM IDs declared
in `Infra/Setup/terraform.tfvars` exist on `NODE01_NAME` and are running.
Provide `PROXMOX_API_URL`, `PROXMOX_API_TOKEN` and `NODE01_NAME` in the environment.
No third-party Python dependencies are required.

```bash
python3 Scripts/check-proxmox-vms.py --tfvars Infra/Setup/terraform.tfvars
# For the current self-signed Proxmox setup, add --insecure.
```

Exit code `0` means ready, `2` means missing/stopped VMs, and `1` means the check
failed (configuration, API, authentication, network, TLS or response errors).
Never interpret every nonzero exit code as permission to provision infrastructure.

## Development & Testing Seeders

- `seed.py`: Central seeding script that populates example proposals (`proposal.json` and workbooks)
  and mapping packages (`MPackage.json`) directly into the shared SFTP server (under `/Proposals/`
  and `/Packages/`) or local development storage (`--local`).

```bash
# Seed both proposals and mapping packages to SFTP (configured in .env)
python3 Scripts/seed.py

# Overwrite existing proposals and mapping packages
python3 Scripts/seed.py --force

# Seed to local storage folder instead of SFTP
python3 Scripts/seed.py --local

# Seed only proposals or only mapping packages
python3 Scripts/seed.py --proposals
python3 Scripts/seed.py --packages
```

## Service CD helpers

- `smoke-service-image.sh`: starts a local image with a read-only root filesystem,
  checks HTTP health, and checks SPA routing for Frontend. Set `IMAGE` and
  `SERVICE_PATH`; it removes its container when finished.
- `registry-pull-secret.py`: emits a Kubernetes registry Secret from
  `GHCR_USERNAME`, `GHCR_TOKEN` and `NAMESPACE`; pipe directly to `kubectl apply`.
- `preserve-cd-images.py`: preserves live service-CD image digests when full
  Kubernetes manifests are reconciled. Reads desired JSON from stdin and accepts
  the live Deployment list with `--live`.
- `select-service-release.cjs`: selects the exact Testing CI image artifact, or
  a successful Testing deployment with matching service source for production.
- `publish-service-image.sh`: loads and publishes CI's saved container without
  rebuilding it. Requires `SERVICE_PATH`, `SOURCE_SHA`, `IMAGE_BASE`, `RUNNER_TEMP`
  and `GITHUB_OUTPUT`.
- `service-release.py`: writes or validates the Testing `release.json` artifact.
  Production uses its immutable GHCR digest, after checking the service, source
  tree, original build commit and image repository.

Run the read-only infrastructure/CD tests with:

```bash
python3 -m unittest discover -s Scripts/tests -p 'test_*.py'
node Scripts/tests/test_service_workflows.cjs
```

The Node.js scenarios exercise CD's selection script with mocked GitHub responses.
They check different merge commit SHAs with identical service source, manual
recovery, stale revisions and rejection of untrusted or missing release artifacts.
Python tests also exercise publishing with a Docker stub; they never push images
or change a cluster.
