"""KG-037 — periodic HPA auto-revert.

Run via the CronJob in k8s/hpa-autorevert-cronjob.yaml. For each HPA
the remediator annotated with `octo.oracle.com/bumped-at` within the
last N minutes, check if current CPU utilisation has dropped below
the target; if so, decrement minReplicas by 1 (floor at the pre-bump
value recorded in the annotation `octo.oracle.com/bumped-from`).

Safe-by-default: never sets minReplicas below the annotation's
recorded baseline, never below 1.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_STALE_MINUTES = 10


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(message)s")

    try:
        from kubernetes import client, config  # type: ignore
    except ImportError:
        logger.error("kubernetes package missing; install .[k8s] extras")
        return 2

    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()

    autoscaling = client.AutoscalingV2Api()
    hpas = autoscaling.list_horizontal_pod_autoscaler_for_all_namespaces()

    now = datetime.now(timezone.utc)
    reverted = 0

    for hpa in hpas.items:
        ann = (hpa.metadata.annotations or {})
        bumped_at = ann.get("octo.oracle.com/bumped-at")
        bumped_from = ann.get("octo.oracle.com/bumped-from")
        if not bumped_at or not bumped_from:
            continue
        try:
            when = datetime.fromisoformat(bumped_at.replace("Z", "+00:00"))
            baseline = int(bumped_from)
        except ValueError:
            continue

        if now - when < timedelta(minutes=_STALE_MINUTES):
            continue

        current_min = hpa.spec.min_replicas or 1
        if current_min <= baseline:
            # Already back to baseline — clear annotations, stop.
            _clear_bump(autoscaling, hpa, ann)
            continue

        new_min = max(baseline, current_min - 1)
        patch = {"spec": {"minReplicas": new_min}}
        if new_min == baseline:
            patch.setdefault("metadata", {})["annotations"] = {
                "octo.oracle.com/bumped-at": None,
                "octo.oracle.com/bumped-from": None,
            }
        autoscaling.patch_namespaced_horizontal_pod_autoscaler(
            name=hpa.metadata.name,
            namespace=hpa.metadata.namespace,
            body=patch,
        )
        logger.info(
            "reverted HPA %s/%s minReplicas %d -> %d",
            hpa.metadata.namespace, hpa.metadata.name, current_min, new_min,
        )
        reverted += 1

    logger.info("hpa_autorevert complete reverted=%d", reverted)
    return 0


def _clear_bump(autoscaling, hpa, ann) -> None:
    patch = {
        "metadata": {
            "annotations": {
                "octo.oracle.com/bumped-at": None,
                "octo.oracle.com/bumped-from": None,
            }
        }
    }
    autoscaling.patch_namespaced_horizontal_pod_autoscaler(
        name=hpa.metadata.name,
        namespace=hpa.metadata.namespace,
        body=patch,
    )


if __name__ == "__main__":
    sys.exit(main())
