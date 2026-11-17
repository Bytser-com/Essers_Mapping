#!/usr/bin/env python3
"""Read-only Proxmox preflight: 0 = ready, 2 = missing/stopped, 1 = check failed."""

import argparse
import json
import os
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


VM_ROLES = ("pipeline_runner", "k8s_master", "k8s_worker")


def expected_vms(tfvars):
    content = Path(tfvars).read_text(encoding="utf-8")
    expected = {}
    for role in VM_ROLES:
        matches = re.findall(
            rf"^\s*{role}_vm_id\s*=\s*(\d+)\s*(?:#.*)?$", content, re.MULTILINE
        )
        if len(matches) != 1:
            raise ValueError(f"Expected one numeric {role}_vm_id in {tfvars}")
        expected[role] = int(matches[0])
    if len(set(expected.values())) != len(expected):
        raise ValueError("Terraform VM IDs must be unique")
    return expected


def fetch_vms(api_url, token, node, insecure=False):
    parsed = urlsplit(api_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("PROXMOX_API_URL must be an HTTPS URL without credentials")
    base = api_url.rstrip("/")
    if not base.endswith("/api2/json"):
        base += "/api2/json"
    request = Request(
        f"{base}/nodes/{quote(node, safe='')}/qemu",
        headers={"Authorization": f"PVEAPIToken={token}", "Accept": "application/json"},
    )
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    with urlopen(request, timeout=30, context=context) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Proxmox returned an unexpected VM-list response")
    # Treat malformed responses as errors, never as proof that VMs are absent.
    for vm in payload["data"]:
        if (
            not isinstance(vm, dict)
            or type(vm.get("vmid")) is not int
            or not isinstance(vm.get("status"), str)
        ):
            raise ValueError("Proxmox returned an invalid VM entry")
    return payload["data"]


def unavailable_vms(expected, actual):
    by_id = {vm["vmid"]: vm for vm in actual}
    return [
        f"{role} (VM {vmid}): "
        + ("missing" if vmid not in by_id else f"status={by_id[vmid]['status']}")
        for role, vmid in expected.items()
        if vmid not in by_id or by_id[vmid]["status"] != "running"
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tfvars", default="Infra/Setup/terraform.tfvars")
    parser.add_argument("--insecure", action="store_true", help="Match a self-signed Proxmox setup")
    args = parser.parse_args()
    try:
        config = {}
        for key in ("PROXMOX_API_URL", "PROXMOX_API_TOKEN", "NODE01_NAME"):
            config[key] = os.environ.get(key, "").strip()
            if not config[key]:
                raise ValueError(f"{key} is missing or empty")
        expected = expected_vms(args.tfvars)
        actual = fetch_vms(
            config["PROXMOX_API_URL"], config["PROXMOX_API_TOKEN"],
            config["NODE01_NAME"], args.insecure,
        )
        unavailable = unavailable_vms(expected, actual)
    except HTTPError as error:
        print(f"Proxmox check failed: HTTP {error.code}. Check API credentials and permissions.", file=sys.stderr)
        return 1
    except (OSError, URLError, ValueError) as error:
        print(f"Proxmox check failed: {error}", file=sys.stderr)
        return 1
    if unavailable:
        print("Infrastructure is not ready: " + "; ".join(unavailable), file=sys.stderr)
        print("Run Terraform apply/start the VMs before configuring or deploying.", file=sys.stderr)
        return 2
    print("All Terraform-defined VMs exist and are running on the configured Proxmox node.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
