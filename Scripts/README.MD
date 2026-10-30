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

## Service CD helpers

- `smoke-service-image.sh`: starts a local image with a read-only root filesystem,
  checks HTTP health, and checks SPA routing for Frontend. Set `IMAGE` and
  `SERVICE_PATH`; it removes its container when finished.
- `registry-pull-secret.py`: emits a Kubernetes registry Secret from
  `GHCR_USERNAME`, `GHCR_TOKEN` and `NAMESPACE`; pipe directly to `kubectl apply`.
- `preserve-cd-images.py`: preserves live service-CD image digests when full
  Kubernetes manifests are reconciled. Reads desired JSON from stdin and accepts
  the live Deployment list with `--live`.

Run the read-only infrastructure/CD tests with:

```bash
python3 -m unittest discover -s Scripts/tests -p 'test_*.py'
```
