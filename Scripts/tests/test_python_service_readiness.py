"""Prevent incomplete Python services from being mistaken for placeholders."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "python_service_readiness", Path(__file__).parents[1] / "python-service-readiness.py"
)
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def test_readme_only_service_defers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.MD").touch()
            self.assertFalse(readiness.is_ready(root))

    def test_code_without_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").touch()
            with self.assertRaisesRegex(ValueError, "requirements.txt"):
                readiness.is_ready(root)

    def test_tests_without_manifest_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            with self.assertRaises(ValueError):
                readiness.is_ready(root)

    def test_manifest_without_tests_fails(self):
        for manifest in ("requirements.txt", "pyproject.toml"):
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / manifest).touch()
                with self.assertRaisesRegex(ValueError, "tests/"):
                    readiness.is_ready(root)

    def test_both_manifest_types_activate_with_tests(self):
        for manifest in ("requirements.txt", "pyproject.toml"):
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / manifest).touch()
                (root / "tests").mkdir()
                self.assertTrue(readiness.is_ready(root))

    def test_missing_service_directory_fails(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "Missing service"):
            readiness.is_ready(Path(directory) / "absent")


if __name__ == "__main__":
    unittest.main()
