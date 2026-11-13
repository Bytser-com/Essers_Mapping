"""Exercise service filtering with real Git commits, including release races."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "detect_service_changes", Path(__file__).parents[1] / "detect-service-changes.py"
)
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


class ChangeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_directory = Path.cwd()
        self.root = Path(self.directory.name)
        os.chdir(self.root)
        self.git("init", "-q")
        self.git("config", "user.name", "CI test")
        self.git("config", "user.email", "ci@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("Runtime/App.java")
        self.write("README.md")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        os.chdir(self.previous_directory)
        self.directory.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout

    def write(self, filename):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")

    def commit(self):
        self.git("add", ".")
        # Avoid editor configuration and signing hooks in the developer's setup.
        subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "commit", "-q", "--file=-"],
            input="CI fixture\n", text=True, check=True, capture_output=True,
        )

    def changed(self, event="pull_request", branch="Development", base=None, shared=""):
        return changes.needs_checks(
            event, branch, self.base if base is None else base,
            "Runtime", ".github/workflows/runtime-ci.yml", shared,
        )

    def test_unrelated_changes_skip_on_pr_and_development(self):
        self.write("docs/new.md")
        self.commit()
        self.assertFalse(self.changed())
        self.assertFalse(self.changed(event="push"))

    def test_service_change_runs_checks(self):
        self.write("Runtime/New.java")
        self.commit()
        self.assertTrue(self.changed())

    def test_move_out_of_service_still_runs_checks(self):
        self.git("mv", "Runtime/App.java", "App.java")
        self.commit()
        self.assertTrue(self.changed())

    def test_shared_workflow_and_helper_changes_run_checks(self):
        self.write("Scripts/shared.py")
        self.commit()
        self.assertTrue(self.changed(shared="\nScripts/shared.py\n"))

    def test_unrelated_commit_skips_on_release_branches(self):
        self.write("Runtime/New.java")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()
        self.write("docs/new.md")
        self.commit()
        for branch in ("Testing", "main"):
            with self.subTest(branch=branch):
                self.assertFalse(self.changed(event="push", branch=branch))

    def test_manual_new_branch_and_missing_base_run_checks(self):
        self.assertTrue(self.changed(event="workflow_dispatch"))
        for base in ("", "0" * 40, "f" * 40):
            with self.subTest(base=base):
                self.assertTrue(self.changed(base=base))


if __name__ == "__main__":
    unittest.main()
