"""Write a registry Secret to stdout for piping directly into kubectl apply."""

import base64
import json
import os


def registry_secret(username, token, namespace):
    if not username or not token or not namespace:
        raise ValueError("GHCR_USERNAME, GHCR_TOKEN and NAMESPACE are required")
    credentials = {"auths": {"ghcr.io": {"auth": base64.b64encode(f"{username}:{token}".encode()).decode()}}}
    return {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": "ghcr-pull-secret", "namespace": namespace},
        "type": "kubernetes.io/dockerconfigjson",
        "data": {".dockerconfigjson": base64.b64encode(json.dumps(credentials).encode()).decode()},
    }


if __name__ == "__main__":
    print(json.dumps(registry_secret(
        os.environ.get("GHCR_USERNAME"), os.environ.get("GHCR_TOKEN"), os.environ.get("NAMESPACE"),
    )))
