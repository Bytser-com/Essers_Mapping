"""Infrastructure preflight contracts; these tests never contact Proxmox."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


SCRIPT = Path(__file__).resolve().parents[1] / "check-proxmox-vms.py"
SPEC = importlib.util.spec_from_file_location("check_proxmox_vms", SCRIPT)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

EXPECTED = {"pipeline_runner": 300, "k8s_master": 100, "k8s_worker": 200}
RUNNING = [{"vmid": vmid, "status": "running"} for vmid in EXPECTED.values()]
CONFIG = {
    "PROXMOX_API_URL": "https://proxmox.invalid:8006/api2/json",
    "PROXMOX_API_TOKEN": "test-user@pve!test-token=not-a-real-secret",
    "NODE01_NAME": "test-node",
}


class InfrastructureCheckTests(unittest.TestCase):
    def test_vm_ids_come_from_terraform_file(self):
        actual = check.expected_vms(SCRIPT.parent.parent / "Infra/Setup/terraform.tfvars")
        self.assertEqual(set(actual), set(EXPECTED))
        self.assertEqual(len(set(actual.values())), 3)

    def test_invalid_or_duplicate_vm_ids_are_configuration_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            tfvars = Path(directory) / "terraform.tfvars"
            for contents in (
                "pipeline_runner_vm_id = 300\n",
                "pipeline_runner_vm_id = 100\nk8s_master_vm_id = 100\nk8s_worker_vm_id = 200\n",
                "pipeline_runner_vm_id = var.id\nk8s_master_vm_id = 100\nk8s_worker_vm_id = 200\n",
            ):
                with self.subTest(contents=contents):
                    tfvars.write_text(contents, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        check.expected_vms(tfvars)

    def test_unrelated_vms_do_not_affect_readiness(self):
        self.assertEqual(check.unavailable_vms(EXPECTED, RUNNING + [{"vmid": 999, "status": "stopped"}]), [])

    def test_missing_and_stopped_vms_are_not_ready(self):
        actual = [{"vmid": 300, "status": "running"}, {"vmid": 100, "status": "stopped"}]
        problems = check.unavailable_vms(EXPECTED, actual)
        self.assertEqual(len(problems), 2)
        self.assertIn("status=stopped", problems[0])
        self.assertIn("missing", problems[1])

    def test_api_request_is_read_only_authenticated_and_has_timeout(self):
        response = io.BytesIO(json.dumps({"data": RUNNING}).encode())
        with patch.object(check, "urlopen", return_value=response) as request:
            self.assertEqual(check.fetch_vms(CONFIG["PROXMOX_API_URL"], CONFIG["PROXMOX_API_TOKEN"], "test node"), RUNNING)
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_method(), "GET")
        self.assertEqual(sent.full_url, "https://proxmox.invalid:8006/api2/json/nodes/test%20node/qemu")
        self.assertEqual(sent.get_header("Authorization"), f"PVEAPIToken={CONFIG['PROXMOX_API_TOKEN']}")
        self.assertEqual(request.call_args.kwargs["timeout"], 30)
        self.assertTrue(request.call_args.kwargs["context"].check_hostname)

    def test_self_signed_mode_is_explicit(self):
        with patch.object(check, "urlopen", return_value=io.BytesIO(b'{"data": []}')) as request:
            check.fetch_vms("https://proxmox.invalid:8006", "token", "node", insecure=True)
        self.assertFalse(request.call_args.kwargs["context"].check_hostname)

    def test_invalid_urls_fail_before_network_access(self):
        with patch.object(check, "urlopen") as request:
            for url in ("http://proxmox.invalid", "https://user:password@proxmox.invalid", "https://proxmox.invalid?token=x"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    check.fetch_vms(url, "token", "node")
            request.assert_not_called()

    def test_malformed_api_data_is_an_error(self):
        for payload in ({}, {"data": {}}, {"data": [None]}, {"data": [{"vmid": True, "status": "running"}]}, {"data": [{"vmid": 100}]}):
            with self.subTest(payload=payload):
                response = io.BytesIO(json.dumps(payload).encode())
                with patch.object(check, "urlopen", return_value=response), self.assertRaises(ValueError):
                    check.fetch_vms(CONFIG["PROXMOX_API_URL"], "token", "node")

    def run_main(self, actual=None, failure=None, config=CONFIG):
        args = [str(SCRIPT), "--tfvars", "unused-fixture"]
        output = io.StringIO()
        with (
            patch.object(check.sys, "argv", args),
            patch.dict(check.os.environ, config, clear=True),
            patch.object(check, "expected_vms", return_value=EXPECTED),
            patch.object(check, "fetch_vms", return_value=actual, side_effect=failure) as fetch,
            redirect_stderr(output), redirect_stdout(output),
        ):
            result = check.main()
        self.assertNotIn(CONFIG["PROXMOX_API_TOKEN"], output.getvalue())
        return result, output.getvalue(), fetch

    def test_main_exit_codes_distinguish_absence_from_errors(self):
        self.assertEqual(self.run_main(actual=RUNNING)[0], 0)
        self.assertEqual(self.run_main(actual=[])[0], 2)
        for failure in (
            HTTPError(CONFIG["PROXMOX_API_URL"], 401, "unauthorized", {}, None),
            HTTPError(CONFIG["PROXMOX_API_URL"], 403, "forbidden", {}, None),
            URLError("connection refused"), TimeoutError("timed out"),
            ValueError("malformed response"),
        ):
            with self.subTest(failure=failure):
                self.assertEqual(self.run_main(failure=failure)[0], 1)

    def test_missing_configuration_never_calls_api(self):
        code, output, fetch = self.run_main(config={})
        self.assertEqual(code, 1)
        self.assertIn("missing or empty", output)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
