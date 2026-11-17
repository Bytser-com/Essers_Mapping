"""Exercise the real Gemini CD shell steps with dummy credentials and no cluster."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
KEY = "dummy-gemini-key"


def workflow_step(filename, name):
    workflow = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
    step = workflow.split(f"      - name: {name}\n", 1)[1].split("\n      - name:", 1)[0]
    script = step.split("        run: |\n", 1)[1]
    return "\n".join(line.removeprefix("          ") for line in script.splitlines())


@unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash is required for workflow shell tests")
class GeminiCdTests(unittest.TestCase):
    def run_script(self, script, directory, key=KEY, prefix=""):
        environment = {
            **os.environ,
            "GEMINI_API_KEY": key,
            "GHCR_USERNAME": "dummy-user",
            "GHCR_TOKEN": "dummy-registry-token",
            "SFTP_SHARED_ADMIN_PASSWORD": "", "SFTP_SHARED_PASSWORD": "",
            "SFTP_RUNTIME_ADMIN_PASSWORD": "", "SFTP_RUNTIME_PASSWORD": "",
            "ACME_EMAIL": "", "DOMAIN_NAME": "",
            "CAPTURE_CALLS": (directory / "calls.txt").as_posix(),
            "CAPTURE_SECRET": (directory / "secret.json").as_posix(),
        }
        return subprocess.run(
            [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", prefix + script],
            cwd=directory, env=environment, capture_output=True, text=True, check=False,
        )

    def test_service_cd_creates_secret_in_selected_namespace_without_logging_key(self):
        script = workflow_step("service-cd.yml", "Configure Mapping Proposal Gemini credentials")
        # kubectl is stubbed: capture arguments and consume the generated manifest.
        stub = """
kubectl() {
  printf '%s\\n' "$@" >> "$CAPTURE_CALLS"
  if [[ "$1" == create ]]; then
    printf '{"kind":"Secret"}'
  else
    cat > "$CAPTURE_SECRET"
  fi
}
"""
        for namespace in ("essers-mapping-testing", "essers-mapping-production"):
            with self.subTest(namespace=namespace), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                result = self.run_script(script, directory, prefix=stub + f"NAMESPACE={namespace}\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = (directory / "calls.txt").read_text().splitlines()
                self.assertIn(f"--from-literal=GEMINI_API_KEY={KEY}", calls)
                self.assertEqual(calls[calls.index("--namespace") + 1], namespace)
                self.assertIn("--dry-run=client", calls)
                self.assertEqual(json.loads((directory / "secret.json").read_text()), {"kind": "Secret"})
                self.assertNotIn(KEY, result.stdout + result.stderr)

    def test_service_cd_rejects_missing_key_before_calling_kubectl(self):
        script = workflow_step("service-cd.yml", "Configure Mapping Proposal Gemini credentials")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = self.run_script(script, directory, key="")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Set GEMINI_API_KEY", result.stderr)
            self.assertFalse((directory / "calls.txt").exists())

    def test_full_kubernetes_cd_requires_key_before_live_changes(self):
        script = workflow_step(
            "kubernetes-deploy.yml", "Require registry and Gemini credentials before live deployment",
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertEqual(self.run_script(script, directory).returncode, 0)
            missing = self.run_script(script, directory, key="")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("Set GEMINI_API_KEY", missing.stderr)

    def test_full_kubernetes_cd_populates_secret_template_without_logging_key(self):
        script = workflow_step("kubernetes-deploy.yml", "Inject environment secrets into manifests")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            template = directory / "base/common/secrets.yaml"
            template.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "Kubernetes/base/common/secrets.yaml", template)
            result = self.run_script(script, directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = template.read_text()
            self.assertIn(f'GEMINI_API_KEY: "{KEY}"', rendered)
            self.assertNotIn("CHANGE_ME_GEMINI_API_KEY", rendered)
            self.assertNotIn(KEY, result.stdout + result.stderr)


class GeminiDeploymentPatchTests(unittest.TestCase):
    def test_image_and_key_refresh_use_one_patch_only_for_mapping_proposal(self):
        script = workflow_step("service-cd.yml", "Deploy only the selected service and wait for rollout")
        python = re.search(r"patch=\$\(python3 -c '\n(.*?)\n'\)", script, re.DOTALL).group(1)
        for deployment in ("mapping-proposal", "frontend", "runtime-backend", "mapping-converter"):
            with self.subTest(deployment=deployment):
                environment = {
                    **os.environ, "DEPLOYMENT": deployment, "IMAGE": "ghcr.io/example/service@sha256:abc",
                    "SOURCE_SHA": "revision", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2",
                }
                result = subprocess.run(
                    [sys.executable, "-c", python], env=environment, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                patch = json.loads(result.stdout)
                template = patch["spec"]["template"]
                self.assertEqual(template["spec"]["containers"], [{"name": deployment, "image": environment["IMAGE"]}])
                self.assertEqual(patch["metadata"]["annotations"]["essers.io/source-sha"], "revision")
                if deployment == "mapping-proposal":
                    self.assertEqual(template["metadata"]["annotations"]["essers.io/gemini-deploy-run"], "42-2")
                else:
                    self.assertNotIn("metadata", template)


if __name__ == "__main__":
    unittest.main()
