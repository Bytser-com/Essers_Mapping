"""Record a deployed Testing image, or validate it before production promotion."""
import argparse
import json
import os
import re
from pathlib import Path


def validate(record, service, tree, image, source_sha):
    if not isinstance(record, dict):
        raise ValueError("Testing release must be a JSON object")
    expected = {"schema": 1, "environment": "Testing", "service": service, "source_tree": tree, "source_sha": source_sha}
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError("Testing release does not match the service source being promoted")
    if not re.fullmatch(r"[a-f0-9]{40}", tree) or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("Invalid source revision in Testing release")
    if not re.fullmatch(re.escape(image) + r"@sha256:[a-f0-9]{64}", record.get("image", "")):
        raise ValueError("Testing release must reference the expected GHCR image by digest")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["write", "read"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    service, tree, image = (os.environ[key] for key in ("SERVICE_PATH", "SOURCE_TREE", "IMAGE_BASE"))
    source_sha = os.environ["IMAGE_SOURCE_SHA"]
    if args.command == "write":
        record = {"schema": 1, "environment": "Testing", "service": service,
                  "source_tree": tree, "source_sha": source_sha, "image": os.environ["IMAGE"],
                  "ci_run_id": os.environ["CI_RUN_ID"]}
        validate(record, service, tree, image, source_sha)
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    else:
        record = validate(json.loads(args.path.read_text(encoding="utf-8")), service, tree, image, source_sha)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"image={record['image']}\nsource-sha={record['source_sha']}\n")
        print(f"Promoting tested image: {record['image']}")


if __name__ == "__main__":
    main()
