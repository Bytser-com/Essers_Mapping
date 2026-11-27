from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import Scripts.seed as seed_mod


class TestSeed(unittest.TestCase):
    def test_examples_defined(self):
        self.assertGreaterEqual(len(seed_mod.PROPOSAL_EXAMPLES), 1)
        self.assertGreaterEqual(len(seed_mod.PACKAGE_EXAMPLES), 1)

    def test_seed_local_both(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            props_dir = base / "proposals"
            pkgs_dir = base / "packages"

            props, pkgs = seed_mod.seed_local(props_dir, pkgs_dir, force=True)

            self.assertGreaterEqual(len(props), 1)
            self.assertGreaterEqual(len(pkgs), 1)

            # Check proposal metadata
            sample_prop = props_dir / "voorbeeldbedrijf-d" / "v3" / "inbound" / "proposal.json"
            self.assertTrue(sample_prop.is_file())
            data = json.loads(sample_prop.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "RETURNED")
            self.assertIn("ai_review", data)
            self.assertEqual(data["ai_review"]["decision"], "REJECTED")

            # Check mapping package
            nouryon_pkg = pkgs_dir / "nouryon" / "v1" / "inbound" / "MPackage.json"
            self.assertTrue(nouryon_pkg.is_file())
            pkg_data = json.loads(nouryon_pkg.read_text(encoding="utf-8"))
            self.assertEqual(pkg_data["schema_version"], "1.0")
            self.assertEqual(pkg_data["meta"]["client_name"], "nouryon")

    def test_seed_local_filter_by_client(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            props_dir = base / "proposals"
            pkgs_dir = base / "packages"

            props, pkgs = seed_mod.seed_local(props_dir, pkgs_dir, force=True, client="nouryon")
            self.assertEqual(len(props), 0)
            self.assertEqual(len(pkgs), 6)  # 5 MPackage.json files + 1 active.json

            nouryon_pkg_v1 = pkgs_dir / "nouryon" / "v1" / "inbound" / "MPackage.json"
            self.assertTrue(nouryon_pkg_v1.is_file())

            nouryon_pkg_v3 = pkgs_dir / "nouryon" / "v3" / "inbound" / "MPackage.json"
            self.assertTrue(nouryon_pkg_v3.is_file())

            nouryon_active = pkgs_dir / "nouryon" / "active.json"
            self.assertTrue(nouryon_active.is_file())
            active_data = json.loads(nouryon_active.read_text(encoding="utf-8"))
            self.assertEqual(active_data["inbound"]["version"], "v3")

            brunos_pkg = pkgs_dir / "brunos" / "v1" / "outbound" / "MPackage.json"
            self.assertFalse(brunos_pkg.exists())

    def test_seed_local_does_not_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            pkgs_dir = base / "packages"
            seed_mod.seed_local(None, pkgs_dir, force=True, client="nouryon")

            folder = pkgs_dir / "nouryon" / "v1" / "inbound"
            pkg_file = folder / "MPackage.json"
            pkg_file.write_text('{"custom": true}', encoding="utf-8")
            active_file = pkgs_dir / "nouryon" / "active.json"
            active_file.write_text('{"custom": true}', encoding="utf-8")

            props, pkgs = seed_mod.seed_local(None, pkgs_dir, force=False, client="nouryon")
            self.assertEqual(len(pkgs), 0)
            self.assertEqual(pkg_file.read_text(encoding="utf-8"), '{"custom": true}')
            self.assertEqual(active_file.read_text(encoding="utf-8"), '{"custom": true}')


if __name__ == "__main__":
    unittest.main()
