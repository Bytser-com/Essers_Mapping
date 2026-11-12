"""Defer empty Python services, but reject incomplete implementations."""

import os
import sys
from pathlib import Path


def is_ready(service):
    if not service.is_dir():
        raise ValueError(f"Missing service directory: {service}")
    manifest = (service / "requirements.txt").is_file() or (service / "pyproject.toml").is_file()
    if not manifest:
        if (service / "tests").exists() or any(service.rglob("*.py")):
            raise ValueError(f"{service}: add requirements.txt or an installable pyproject.toml.")
        return False
    if not (service / "tests").is_dir():
        raise ValueError(f"{service}: add automated tests under tests/.")
    return True


def main():
    service = Path(sys.argv[1])
    try:
        enabled = is_ready(service)
    except ValueError as error:
        print(f"::error::{error}")
        return 1
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"enabled={str(enabled).lower()}\n")
    if not enabled:
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(f"{service} is a placeholder; Python checks and coverage are deferred.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
