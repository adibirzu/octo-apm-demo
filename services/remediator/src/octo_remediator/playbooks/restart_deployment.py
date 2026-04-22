"""Tier-high playbook: rollout-restart a Deployment.

Always requires operator approval — restarting kills in-flight
connections. The playbook proposes; the POST /runs/{id}/approve
endpoint commits.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import ExecutionContext, Playbook, RemediationTier, _now_iso

logger = logging.getLogger(__name__)


class RestartDeploymentPlaybook(Playbook):
    name = "restart-deployment"
    description = "kubectl rollout restart — drops in-flight connections; operator-approved only."
    tier = RemediationTier.HIGH

    def matches(self, alarm: dict[str, Any]) -> bool:
        body = (alarm.get("body") or "").lower()
        return "deployment unhealthy" in body or "pod crashloop" in body

    def extract_params(self, alarm: dict[str, Any]) -> dict[str, Any]:
        ann = alarm.get("annotations") or {}
        return {
            "namespace": ann.get("target_namespace", "octo-shop-prod"),
            "deployment": ann.get("target_deployment", "octo-drone-shop"),
        }

    async def execute(self, ctx: ExecutionContext) -> list[dict[str, Any]]:
        namespace = ctx.run.params["namespace"]
        deployment = ctx.run.params["deployment"]

        action_started = _now_iso()
        if ctx.dry_run:
            return [{
                "kind": "rollout_restart_dryrun",
                "target": f"{namespace}/{deployment}",
                "result": "would patch spec.template.metadata.annotations.kubectl.kubernetes.io/restartedAt",
                "completed_at": _now_iso(),
            }]

        try:
            from kubernetes import client, config  # type: ignore
        except ImportError:
            return [{
                "kind": "rollout_restart",
                "target": f"{namespace}/{deployment}",
                "result": "skipped — kubernetes client not installed",
                "completed_at": _now_iso(),
            }]

        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        apps = client.AppsV1Api()
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": _now_iso(),
                            "octo.oracle.com/restart-reason": f"remediator:{ctx.run.run_id}",
                        }
                    }
                }
            }
        }
        apps.patch_namespaced_deployment(
            name=deployment, namespace=namespace, body=patch
        )

        return [{
            "kind": "rollout_restart",
            "target": f"{namespace}/{deployment}",
            "result": "patched restartedAt annotation",
            "started_at": action_started,
            "completed_at": _now_iso(),
        }]
