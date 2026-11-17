#!/usr/bin/env python3
"""
Grafana Dashboard GitOps Importer
Wraps an exported Grafana dashboard JSON file into a Kubernetes ConfigMap
with the required GitOps sidecar labels and annotations for automated deployment.

Usage:
    python3 Scripts/import-grafana-dashboard.py path/to/dashboard.json
    python3 Scripts/import-grafana-dashboard.py path/to/dashboard.json --name "custom-metrics"
"""

import argparse
import json
import re
import sys
from pathlib import Path

def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\-]", "-", name.lower())
    return re.sub(r"-+", "-", cleaned).strip("-")

def main():
    parser = argparse.ArgumentParser(description="Wrap exported Grafana dashboard JSON into a GitOps ConfigMap")
    parser.add_argument("file", type=Path, help="Path to exported Grafana dashboard JSON file")
    parser.add_argument("--name", type=str, help="Custom identifier name (defaults to file stem or dashboard title)")
    parser.add_argument("--folder", type=str, default="essers", help="Target dashboard folder in Grafana (default: essers)")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            dashboard_data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON from {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine dashboard name
    raw_title = args.name or dashboard_data.get("title") or args.file.stem
    slug = sanitize_name(raw_title)
    cm_name = f"grafana-dashboard-{slug}"
    json_filename = f"{slug}.json"

    # Destination directory
    repo_root = Path(__file__).resolve().parent.parent
    dest_dir = repo_root / "Kubernetes" / "cluster-addons" / "monitoring" / "dashboards"
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / f"{slug}-cm.yaml"

    # Indent JSON inside ConfigMap data
    formatted_json = json.dumps(dashboard_data, indent=2)
    indented_json = "\n".join("    " + line for line in formatted_json.splitlines())

    manifest = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {cm_name}
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
    app.kubernetes.io/part-of: essers-mapping
  annotations:
    k8s-sidecar-target-directory: "/tmp/dashboards/{args.folder}"
data:
  {json_filename}: |
{indented_json}
"""

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(manifest)

    # Update kustomization.yaml if not already present
    kust_file = dest_dir / "kustomization.yaml"
    if kust_file.is_file():
        content = kust_file.read_text(encoding="utf-8")
        cm_filename = f"{slug}-cm.yaml"
        if cm_filename not in content:
            # Append before configMapGenerator or comments
            lines = content.splitlines()
            res_idx = -1
            for i, line in enumerate(lines):
                if line.strip() == "resources:":
                    res_idx = i
                    break
            if res_idx != -1:
                # Find last resource entry
                insert_idx = res_idx + 1
                while insert_idx < len(lines) and lines[insert_idx].strip().startswith("-"):
                    insert_idx += 1
                lines.insert(insert_idx, f"  - {cm_filename}")
                kust_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print(f"Updated {kust_file.relative_to(repo_root)} with {cm_filename}")

    print(f"Successfully generated GitOps dashboard manifest: {out_file.relative_to(repo_root)}")
    print(f"Commit and push this file to deploy automatically through your CI/CD and Ansible pipelines!")

if __name__ == "__main__":
    main()
