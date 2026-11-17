"""CD data handling tests; no registry or Kubernetes connection is made."""

import base64
import copy
import importlib.util
import json
from pathlib import Path
import unittest


def load(name, filename):
    location = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location(name, location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


registry = load("registry_pull_secret", "registry-pull-secret.py")
images = load("preserve_cd_images", "preserve-cd-images.py")
cleanup = load("cleanup_deployment_overrides", "cleanup-deployment-overrides.py")
DIGEST = "ghcr.io/example/repo/frontend@sha256:" + "a" * 64


def deployment(name="frontend", namespace="essers-mapping-testing", managed=False):
    return {
        "kind": "Deployment",
        "metadata": {
            "name": name, "namespace": namespace,
            "annotations": {"essers.io/image-managed-by": "service-cd", "essers.io/source-sha": "b" * 40} if managed else {},
        },
        "spec": {"replicas": 3, "template": {"spec": {"containers": [{"name": name, "image": DIGEST if managed else "bootstrap:v1"}]}}},
    }


class ServiceCdTests(unittest.TestCase):
    def test_registry_secret_contains_only_the_required_registry_credentials(self):
        secret = registry.registry_secret("robot", "fake-token", "essers-mapping-testing")
        data = json.loads(base64.b64decode(secret["data"][".dockerconfigjson"]))
        self.assertEqual(base64.b64decode(data["auths"]["ghcr.io"]["auth"]), b"robot:fake-token")
        self.assertEqual(secret["metadata"], {"name": "ghcr-pull-secret", "namespace": "essers-mapping-testing"})
        self.assertEqual(secret["type"], "kubernetes.io/dockerconfigjson")

    def test_registry_configuration_is_required(self):
        for values in (("", "token", "ns"), ("user", "", "ns"), ("user", "token", "")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                registry.registry_secret(*values)

    def test_managed_image_survives_reconciliation_but_other_configuration_updates(self):
        desired = {"items": [deployment()]}
        live = {"items": [deployment(managed=True)]}
        result = images.preserve_images(desired, live)["items"][0]
        self.assertEqual(result["spec"]["template"]["spec"]["containers"][0]["image"], DIGEST)
        self.assertEqual(result["spec"]["replicas"], 3)
        self.assertEqual(result["metadata"]["annotations"]["essers.io/source-sha"], "b" * 40)

    def test_unmanaged_and_other_namespace_images_follow_manifests(self):
        for existing in (deployment(), deployment(namespace="essers-mapping-production", managed=True)):
            desired = {"items": [deployment()]}
            expected = copy.deepcopy(desired)
            self.assertEqual(images.preserve_images(desired, {"items": [existing]}), expected)

    def test_first_deployment_and_non_deployments_are_unchanged(self):
        desired = {"items": [deployment(), {"kind": "Service", "metadata": {"name": "frontend"}}]}
        expected = copy.deepcopy(desired)
        self.assertEqual(images.preserve_images(desired, {"items": []}), expected)

    def test_mutable_or_external_managed_image_is_rejected(self):
        live = deployment(managed=True)
        for image in ("ghcr.io/example/repo:latest", "example.invalid/image@sha256:" + "a" * 64):
            live["spec"]["template"]["spec"]["containers"][0]["image"] = image
            with self.subTest(image=image), self.assertRaises(ValueError):
                images.preserve_images({"items": [deployment()]}, {"items": [live]})

    def test_services_remain_independent(self):
        desired = {"items": [deployment(), deployment(name="runtime-backend")]}
        result = images.preserve_images(desired, {"items": [deployment(managed=True)]})
        self.assertEqual(result["items"][0]["spec"]["template"]["spec"]["containers"][0]["image"], DIGEST)
        self.assertEqual(result["items"][1]["spec"]["template"]["spec"]["containers"][0]["image"], "bootstrap:v1")

    def test_sidecar_updates_follow_manifests(self):
        desired = deployment()
        live = deployment(managed=True)
        desired["spec"]["template"]["spec"]["containers"].append({"name": "sidecar", "image": "sidecar:v2"})
        live["spec"]["template"]["spec"]["containers"].append({"name": "sidecar", "image": "sidecar:v1"})
        result = images.preserve_images({"items": [desired]}, {"items": [live]})
        self.assertEqual(result["items"][0]["spec"]["template"]["spec"]["containers"][1]["image"], "sidecar:v2")

    def test_load_manifests_handles_concatenated_json_stream(self):
        import io
        stream = io.StringIO(
            json.dumps({"kind": "Namespace", "metadata": {"name": "test-ns"}}) + "\n" +
            json.dumps(deployment())
        )
        loaded = images.load_manifests(stream)
        self.assertEqual(loaded["kind"], "List")
        self.assertEqual(len(loaded["items"]), 2)
        self.assertEqual(loaded["items"][0]["kind"], "Namespace")
        self.assertEqual(loaded["items"][1]["kind"], "Deployment")

    def test_load_manifests_preserves_single_list_object(self):
        import io
        stream = io.StringIO(json.dumps({"kind": "List", "items": [deployment()]}))
        loaded = images.load_manifests(stream)
        self.assertEqual(loaded["kind"], "List")
        self.assertEqual(len(loaded["items"]), 1)
        self.assertEqual(loaded["items"][0]["kind"], "Deployment")

    def test_cleanup_deployment_overrides_removes_command_and_args(self):
        dep = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"name": "sidecar", "image": "busybox"},
                            {"name": "runtime-backend", "image": "busybox", "command": ["/bin/sh"], "args": ["run"]},
                        ]
                    }
                }
            }
        }
        ops = cleanup.build_removal_patch(dep, "runtime-backend")
        self.assertEqual(ops, [
            {"op": "remove", "path": "/spec/template/spec/containers/1/command"},
            {"op": "remove", "path": "/spec/template/spec/containers/1/args"},
        ])

    def test_cleanup_deployment_overrides_noop_when_no_overrides(self):
        dep = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"name": "runtime-backend", "image": "app:v1"}
                        ]
                    }
                }
            }
        }
        self.assertEqual(cleanup.build_removal_patch(dep, "runtime-backend"), [])
        self.assertEqual(cleanup.build_removal_patch(dep, "non-existent"), [])


if __name__ == "__main__":
    unittest.main()
