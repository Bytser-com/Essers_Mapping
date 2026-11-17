"""Regression checks for dependency coverage and fail-closed inventory exports."""

import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "dependency_inventory", Path(__file__).parents[1] / "dependency-inventory.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class Distribution:
    def __init__(self, name, version, direct_url=None):
        self.metadata = {"Name": name}
        self.version = version
        self.direct_url = direct_url

    def read_text(self, name):
        return json.dumps(self.direct_url) if self.direct_url else None


class InventoryTests(unittest.TestCase):
    def test_maven_includes_transitive_and_test_dependencies_but_not_app(self):
        shared = {"groupId": "org.example", "artifactId": "shared", "version": "2"}
        tree = {"groupId": "local", "artifactId": "service", "version": "1", "children": [
            {"groupId": "org.example", "artifactId": "web", "version": "3", "children": [shared]},
            {"groupId": "org.example", "artifactId": "tests", "version": "4", "scope": "test", "children": [shared]},
        ]}
        self.assertEqual(audit.maven_packages(tree), {
            ("Maven", "org.example:web", "3"),
            ("Maven", "org.example:shared", "2"),
            ("Maven", "org.example:tests", "4"),
        })

    def test_invalid_maven_node_fails_instead_of_disappearing(self):
        with self.assertRaises(KeyError):
            audit.maven_packages({"children": [{"groupId": "example", "artifactId": "broken"}]})

    def test_python_includes_test_tools_and_direct_url_wheels(self):
        packages = audit.python_packages([
            Distribution("requests", "2.32.0"),
            Distribution("pytest", "8.0.0"),
            Distribution("wheel-package", "1", {"url": "https://example.org/pkg.whl", "archive_info": {}}),
            Distribution("my-local-service", "0.1", {"url": "file:///service", "dir_info": {}}),
        ])
        self.assertEqual(packages, {
            ("PyPI", "requests", "2.32.0"), ("PyPI", "pytest", "8.0.0"),
            ("PyPI", "wheel-package", "1"),
        })

    def test_python_missing_version_fails(self):
        with self.assertRaises(ValueError):
            audit.python_packages([Distribution("broken", "")])

    def test_empty_inventory_fails(self):
        with self.assertRaises(ValueError):
            audit.inventory(set())

    def test_custom_osv_lockfile_is_deterministic(self):
        result = audit.inventory({("PyPI", "z", "1"), ("Maven", "a:b", "2")})
        self.assertEqual(result["results"][0]["packages"], [
            {"package": {"ecosystem": "Maven", "name": "a:b", "version": "2"}},
            {"package": {"ecosystem": "PyPI", "name": "z", "version": "1"}},
        ])


if __name__ == "__main__":
    unittest.main()
