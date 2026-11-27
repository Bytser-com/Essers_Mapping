"""Validation tests for Kubernetes monitoring manifests, Grafana dashboards, and Discord alerts (Issue 164).

Uses Python standard library only so it runs in every CI/runner environment without extra packages.
"""
from __future__ import annotations

import json
import re
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MON_DIR = REPO_ROOT / "Kubernetes" / "cluster-addons" / "monitoring"
INGRESS_DIR = REPO_ROOT / "Kubernetes" / "cluster-addons" / "ingress-nginx"


def _extract_embedded_json(configmap_text: str) -> dict:
    """Extract the embedded Grafana dashboard JSON block from a ConfigMap YAML."""
    match = re.search(r"^\s+[A-Za-z0-9_.-]+\.json:\s*\|\s*\n((?:[ \t]+.*\n?|\s*\n)*)", configmap_text, re.MULTILINE)
    if not match:
        raise AssertionError("Could not find embedded *.json block in dashboard ConfigMap")
    raw_json = textwrap.dedent(match.group(1)).strip()
    return json.loads(raw_json)


class TestMonitoringConfig(unittest.TestCase):
    def test_helm_values_define_minipc_retention_limits_cluster_labels_and_discord_alerts(self):
        expected = {
            "testing": {
                "file": MON_DIR / "values-testing.yaml",
                "retention": "retention: 7d",
                "retentionSize": "retentionSize: 8GiB",
                "prom_pvc": "storage: 10Gi",
                "badge": "[TESTING]",
                "url": "https://monitor-testing.shystack.com",
            },
            "production": {
                "file": MON_DIR / "values-production.yaml",
                "retention": "retention: 14d",
                "retentionSize": "retentionSize: 12GiB",
                "prom_pvc": "storage: 15Gi",
                "badge": "[PRODUCTION]",
                "url": "https://monitor-production.shystack.com",
            },
        }
        for env, cfg in expected.items():
            with self.subTest(env=env):
                text = cfg["file"].read_text(encoding="utf-8")
                self.assertIn(cfg["retention"], text)
                self.assertIn(cfg["retentionSize"], text)
                self.assertIn(cfg["prom_pvc"], text)
                self.assertIn(f"cluster: {env}", text)
                self.assertIn(f"environment: {env}", text)
                self.assertIn(f"replacement: {env}", text)

                # All monitoring components have bounded requests & limits
                for section in ("prometheusOperator:", "grafana:", "prometheus:", "alertmanager:", "kube-state-metrics:"):
                    self.assertIn(section, text)
                self.assertGreaterEqual(text.count("requests:"), 8)
                self.assertGreaterEqual(text.count("limits:"), 6)

                # Unreachable kubeadm localhost targets disabled
                for disabled in ("kubeEtcd:", "kubeControllerManager:", "kubeScheduler:", "kubeProxy:"):
                    self.assertRegex(text, rf"{disabled}\s*\n\s+enabled:\s*false")

                # Alertmanager Discord config: Watchdog silenced, inhibition rules, env badge, real newlines
                self.assertIn("inhibit_rules:", text)
                self.assertIn('alertname =~ "Watchdog|InfoInhibitor"', text)
                self.assertIn('receiver: "null"', text)
                self.assertIn(
                    'webhook_url: "https://discord.com/api/webhooks/PLACEHOLDER_DISCORD_WEBHOOK_URL"',
                    text,
                )
                self.assertIn(cfg["badge"], text)
                self.assertIn(cfg["url"], text)
                self.assertNotIn("\\n**Description:**", text)
                self.assertIn("message: |-", text)

    def test_dashboards_are_valid_json_registered_in_kustomization_and_have_required_filters(self):
        kustom_text = (MON_DIR / "dashboards" / "kustomization.yaml").read_text(encoding="utf-8")
        expected_dashboards = [
            "k8s-cluster-overview-cm.yaml",
            "essers-proposals-ai-pipeline-cm.yaml",
            "essers-services-overview-cm.yaml",
        ]
        for filename in expected_dashboards:
            self.assertIn(filename, kustom_text)
            cm_text = (MON_DIR / "dashboards" / filename).read_text(encoding="utf-8")
            self.assertIn("kind: ConfigMap", cm_text)
            self.assertIn('grafana_dashboard: "1"', cm_text)

            dash = _extract_embedded_json(cm_text)
            var_names = [v["name"] for v in dash["templating"]["list"]]
            self.assertIn("datasource", var_names, f"{filename} missing datasource variable")
            self.assertIn("cluster", var_names, f"{filename} missing cluster variable")
            self.assertIn("namespace", var_names, f"{filename} missing namespace variable")

            serialized = json.dumps(dash)
            if filename == "k8s-cluster-overview-cm.yaml":
                self.assertIn("pod", var_names)
                for metric in (
                    "container_cpu_usage_seconds_total",
                    "container_memory_working_set_bytes",
                    "container_network_receive_bytes_total",
                    "container_fs_reads_bytes_total",
                    "kubelet_volume_stats_used_bytes",
                    "node_disk_read_bytes_total",
                ):
                    self.assertIn(metric, serialized)
            if filename == "essers-proposals-ai-pipeline-cm.yaml":
                for metric in (
                    "essers_proposals_total",
                    "essers_proposals_failed_total",
                    "essers_proposals_sftp_up",
                    "essers_proposals_oldest_running_age_seconds",
                    "essers_converter_ai_reviews_total",
                ):
                    self.assertIn(metric, serialized)

    def test_prometheus_rules_have_required_groups_alerts_and_annotations(self):
        text = (MON_DIR / "alerts" / "essers-alerts.yaml").read_text(encoding="utf-8")
        self.assertIn("kind: PrometheusRule", text)
        for group in (
            "name: essers-workload-alerts",
            "name: essers-proposal-pipeline-alerts",
            "name: essers-infrastructure-alerts",
        ):
            self.assertIn(group, text)

        expected_alerts = (
            "ServiceZeroReplicasAvailable",
            "PodCrashLooping",
            "PodOOMKilled",
            "PodFrequentRestarts",
            "PodStuckPending",
            "ContainerNearMemoryLimit",
            "ContainerHighCpuThrottling",
            "MappingProposalSftpUnreachable",
            "MappingProposalAiFailed",
            "MappingProposalAiStuck",
            "MappingProposalUploadErrors",
            "MappingConverterAiReviewErrors",
            "PvcStorageSpaceWarning",
            "PvcStorageSpaceCritical",
            "NodeNotReady",
            "NodeHighMemoryUsage",
            "NodeHighDiskUsage",
            "IngressHigh5xxErrorRate",
            "PrometheusTargetDown",
        )
        for alert in expected_alerts:
            self.assertIn(f"alert: {alert}", text)
        self.assertGreaterEqual(text.count("runbook:"), len(expected_alerts))
        self.assertGreaterEqual(text.count("dashboard_uid:"), len(expected_alerts))

    def test_servicemonitors_network_policies_and_ingress_metrics_align(self):
        sm_text = (MON_DIR / "service-monitors" / "essers-mapping-servicemonitor.yaml").read_text(encoding="utf-8")
        self.assertIn("- mapping-proposal", sm_text)
        self.assertIn("- mapping-converter", sm_text)
        self.assertIn("path: /metrics", sm_text)
        self.assertNotIn("/actuator/prometheus", sm_text.split("spec:", 1)[1])

        np_text = (MON_DIR / "network-policies.yaml").read_text(encoding="utf-8")
        self.assertIn("name: allow-prometheus-scrape-monitoring-components", np_text)
        self.assertIn("port: 10254", np_text)
        self.assertIn("port: 9090", np_text)

        for env in ("testing", "production"):
            ing_text = (INGRESS_DIR / f"values-{env}.yaml").read_text(encoding="utf-8")
            self.assertRegex(ing_text, r"metrics:\s*\n\s+enabled:\s*true")


if __name__ == "__main__":
    unittest.main()
