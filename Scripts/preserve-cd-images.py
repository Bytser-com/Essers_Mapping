"""Preserve service-CD image digests during full Kubernetes manifest reconciliation."""

import argparse
import json
import re
import sys


def load_manifests(stream):
    raw = stream.read().strip()
    if not raw:
        return {"items": []}
    decoder = json.JSONDecoder()
    pos = 0
    items = []
    while pos < len(raw):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            break
        obj, end = decoder.raw_decode(raw, idx=pos)
        items.append(obj)
        pos = end
    if len(items) == 1 and isinstance(items[0], dict) and "items" in items[0]:
        return items[0]
    return {"apiVersion": "v1", "kind": "List", "items": items}


def preserve_images(desired, live):
    managed = {}
    for deployment in live.get("items", []):
        metadata = deployment.get("metadata", {})
        if metadata.get("annotations", {}).get("essers.io/image-managed-by") == "service-cd":
            managed[(metadata.get("namespace"), metadata["name"])] = deployment
    resources = desired if isinstance(desired, list) else desired.get("items", [])
    for resource in resources:
        if resource.get("kind") != "Deployment":
            continue
        metadata = resource["metadata"]
        current = managed.get((metadata.get("namespace"), metadata["name"]))
        if not current:
            continue
        containers = {item["name"]: item["image"] for item in current["spec"]["template"]["spec"]["containers"]}
        for container in resource["spec"]["template"]["spec"]["containers"]:
            # Service CD targets the container named after its Deployment.
            # Sidecar versions continue to follow the desired manifests.
            if container["name"] != metadata["name"]:
                continue
            image = containers.get(container["name"])
            if image:
                if not re.fullmatch(r"ghcr\.io/[^@\s]+@sha256:[0-9a-f]{64}", image):
                    raise ValueError(f"Invalid managed image digest on {metadata['name']}")
                container["image"] = image
        annotations = metadata.setdefault("annotations", {})
        annotations["essers.io/image-managed-by"] = "service-cd"
        source_sha = current["metadata"].get("annotations", {}).get("essers.io/source-sha")
        if source_sha:
            annotations["essers.io/source-sha"] = source_sha
    return desired


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", required=True)
    args = parser.parse_args()
    with open(args.live, encoding="utf-8") as live_file:
        live = json.load(live_file)
    json.dump(preserve_images(load_manifests(sys.stdin), live), sys.stdout)

