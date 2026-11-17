"""Export resolved Maven/Python dependencies in OSV's custom lockfile format."""

import argparse
import importlib.metadata
import json
from pathlib import Path


def maven_packages(tree):
    """Include resolved direct/transitive dependencies of every scope, not the app."""
    packages = set()

    def visit(node):
        name = f"{node['groupId']}:{node['artifactId']}"
        packages.add(("Maven", name, node["version"]))
        for child in node.get("children", []):
            visit(child)

    for child in tree.get("children", []):
        visit(child)
    return packages


def python_packages(distributions):
    """Include installed application/test tools; omit the locally installed app."""
    packages = set()
    for distribution in distributions:
        direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
        if "dir_info" in direct_url:
            continue
        name = distribution.metadata["Name"]
        if not name or not distribution.version:
            raise ValueError("Installed dependency has no name or version")
        packages.add(("PyPI", name, distribution.version))
    return packages


def inventory(packages):
    if not packages:
        raise ValueError("No resolved dependencies found; refusing an empty audit")
    return {"results": [{"packages": [
        {"package": {"ecosystem": ecosystem, "name": name, "version": version}}
        for ecosystem, name, version in sorted(packages)
    ]}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--maven-tree", type=Path)
    source.add_argument("--python", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    packages = (
        maven_packages(json.loads(args.maven_tree.read_text(encoding="utf-8")))
        if args.maven_tree else python_packages(importlib.metadata.distributions())
    )
    result = inventory(packages)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
