"""Decide whether a service needs CI, using Git and the GitHub event."""

import os
import subprocess
from pathlib import Path


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def needs_checks(event, branch, base, service, workflow, shared):
    # Each release revision needs artifacts, even after an unrelated push.
    if event == "workflow_dispatch" or (event == "push" and branch in {"Testing", "main"}):
        return True
    if not base or set(base) == {"0"} or git("cat-file", "-e", f"{base}^{{commit}}").returncode:
        return True

    paths = [service, workflow, ".github/actions/service-changes", ".gitattributes"]
    paths.extend(path.strip() for path in shared.splitlines() if path.strip())
    result = git("diff", "--name-only", "--no-renames", base, "HEAD", "--", *paths)
    result.check_returncode()
    return bool(result.stdout.strip())


def main():
    changed = needs_checks(
        os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF_NAME"],
        os.environ.get("BASE_SHA", ""), os.environ["SERVICE_PATH"],
        os.environ["WORKFLOW_PATH"], os.environ.get("SHARED_PATHS", ""),
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"changed={str(changed).lower()}\n")
    print("Service checks required." if changed else "Service unchanged; checks skipped.")


if __name__ == "__main__":
    main()
