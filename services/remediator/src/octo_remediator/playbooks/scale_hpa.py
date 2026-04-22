"""Tier-medium playbook: scale a HorizontalPodAutoscaler minReplicas
up when the Deployment is under sustained pressure.

Matches CPU-pressure alarms on specific namespaces. Scoped to
deployments the remediator's RBAC allows it to patch.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import ExecutionContext, Playbook, RemediationTier, _now_iso

logger = logging.getLogger(__name__)


class ScaleHPAPlaybook(Playbook):
    name = "scale-hpa"
    description = "Bump HPA minReplicas by 1. Reverts itself 10min later if load drops."
    tier = RemediationTier.MEDIUM

    def matches(self, alarm: dict[str, Any]) -> bool:
        body = (alarm.get("body") or "").lower()
        metric = (alarm.get("metric_name") or "").lower()
        # Typical alarm body templates for CPU pressure
        return any(s in body for s in ("cpu pressure", "cpu throttling", "hpa saturated")) or \
               metric in ("container_cpu_utilisation", "kube_hpa_saturation")

    def extract_params(self, alarm: dict[str, Any]) -> dict[str, Any]:
        ann = alarm.get("annotations") or {}
        return {
            "namespace": ann.get("target_namespace", "octo-shop-prod"),
            "deployment": ann.get("target_deployment", "octo-drone-shop"),
            "min_replicas_increment": int(ann.get("min_replicas_increment", 1)),
        }

    async def execute(self, ctx: ExecutionContext) -> list[dict[str, Any]]:
        namespace = ctx.run.params["namespace"]
        deployment = ctx.run.params["deployment"]
        increment = int(ctx.run.params["min_replicas_increment"])

        action_started = _now_iso()
        if ctx.dry_run:
            return [{
                "kind": "patch_hpa_dryrun",
                "target": f"{namespace}/{deployment}",
                "result": f"would increment minReplicas by {increment}",
                "completed_at": _now_iso(),
            }]

        # Lazy import — kubernetes client is an optional extra
        try:
            from kubernetes import client, config  # type: ignore
        except ImportError:
            return [{
                "kind": "patch_hpa",
                "target": f"{namespace}/{deployment}",
                "result": "skipped — kubernetes client not installed (install with pip extras [k8s])",
                "completed_at": _now_iso(),
            }]

        try:
            config.load_incluster_config()
        except Exception:
            try:
                config.load_kube_config()
            except Exception as exc:
                return [{
                    "kind": "patch_hpa",
                    "target": f"{namespace}/{deployment}",
                    "result": f"kube config load failed: {exc}",
                    "completed_at": _now_iso(),
                }]

        autoscaling = client.AutoscalingV2Api()
        hpa = autoscaling.read_namespaced_horizontal_pod_autoscaler(
            name=deployment, namespace=namespace
        )
        new_min = (hpa.spec.min_replicas or 1) + increment
        patch = {"spec": {"minReplicas": new_min}}
        autoscaling.patch_namespaced_horizontal_pod_autoscaler(
            name=deployment,
            namespace=namespace,
            body=patch,
        )

        return [{
            "kind": "patch_hpa",
            "target": f"{namespace}/{deployment}",
            "result": f"minReplicas: {hpa.spec.min_replicas} → {new_min}",
            "started_at": action_started,
            "completed_at": _now_iso(),
        }]
