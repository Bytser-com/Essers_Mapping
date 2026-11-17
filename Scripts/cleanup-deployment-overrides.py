"""Remove leftover container command/args overrides from a live Kubernetes deployment."""

import json
import sys


def build_removal_patch(deployment_json, container_name):
    """Return a list of JSON patch operations to remove command and args for the target container."""
    data = json.loads(deployment_json) if isinstance(deployment_json, str) else deployment_json
    ops = []
    containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    for idx, container in enumerate(containers):
        if container.get("name") == container_name:
            if "command" in container:
                ops.append({"op": "remove", "path": f"/spec/template/spec/containers/{idx}/command"})
            if "args" in container:
                ops.append({"op": "remove", "path": f"/spec/template/spec/containers/{idx}/args"})
    return ops


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: cleanup-deployment-overrides.py <container_name>", file=sys.stderr)
        sys.exit(1)
    target = sys.argv[1]
    patch = build_removal_patch(sys.stdin.read(), target)
    print(json.dumps(patch))
