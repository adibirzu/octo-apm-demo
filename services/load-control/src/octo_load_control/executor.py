"""Run executor dispatch.

Every :class:`ExecutorKind` has a matching function below that turns
a Profile + Run into a live side effect. Dispatch is async so we can
launch a long-running executor and immediately return the run_id to
the caller.

For phases not yet built (K8S_STRESS, VM_STRESS, EDGE_FUZZ, BROWSER_RUNNER
beyond scaffolding), the executor returns a friendly ``NotImplementedYet``
Run state so the control plane + docs are complete today.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from .profiles import ExecutorKind, Profile
from .runs import Run, RunState

logger = logging.getLogger(__name__)


class ExecutorBackend:
    """Function table — one async call per ExecutorKind."""

    def __init__(self, *, traffic_generator_client, chaos_admin_client):
        self._traffic = traffic_generator_client
        self._chaos = chaos_admin_client

    async def dispatch(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        """Launch the executor for ``profile`` and return metadata recorded
        on the Run. Caller is responsible for persisting updates."""
        if profile.executor == ExecutorKind.TRAFFIC_GENERATOR:
            return await self._run_traffic_generator(profile=profile, run=run)
        if profile.executor == ExecutorKind.CHAOS_ADMIN:
            return await self._run_chaos_admin(profile=profile, run=run)
        if profile.executor == ExecutorKind.BROWSER_RUNNER:
            return await self._run_browser_runner(profile=profile, run=run)
        if profile.executor == ExecutorKind.K8S_STRESS:
            return await self._run_k8s_stress(profile=profile, run=run)
        if profile.executor == ExecutorKind.VM_STRESS:
            return await self._run_vm_stress(profile=profile, run=run)
        if profile.executor == ExecutorKind.EDGE_FUZZ:
            return await self._run_edge_fuzz(profile=profile, run=run)
        raise ValueError(f"unknown executor kind: {profile.executor}")

    async def _run_browser_runner(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        """Render the browser-runner K8s Job template and apply via
        subprocess (kubectl). Assumes the operator's kube context is
        already set in the pod — cluster-internal load-control
        deployments use in-cluster config automatically."""
        import subprocess

        journey = profile.executor_args.get("journey", "catalog-to-checkout")
        iterations = int(profile.executor_args.get("iterations", 1))
        env = {
            "RUN_ID": run.run_id,
            "JOURNEY": journey,
            "ITERATIONS": str(iterations),
            "DNS_DOMAIN": os.getenv("DNS_DOMAIN", "octodemo.cloud"),
            "OCIR_REGION": os.getenv("OCIR_REGION", ""),
            "OCIR_TENANCY": os.getenv("OCIR_TENANCY", ""),
            "IMAGE_TAG": os.getenv("IMAGE_TAG", "latest"),
        }
        template = "/app/services/browser-runner/k8s/job.yaml"
        try:
            # envsubst | kubectl apply -f -
            rendered = subprocess.run(
                ["envsubst"],
                stdin=open(template, "r"),  # noqa: SIM115
                capture_output=True,
                text=True,
                env={**os.environ, **env},
            ).stdout
            apply = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=rendered,
                capture_output=True,
                text=True,
            )
            return {
                "status": "launched" if apply.returncode == 0 else "dispatch_error",
                "endpoint": "k8s-job",
                "kubectl_rc": apply.returncode,
                "resource": f"job/browser-runner-{run.run_id}",
            }
        except FileNotFoundError as exc:
            logger.warning("browser-runner dispatch failed (envsubst/kubectl missing): %s", exc)
            return {"status": "dispatch_error", "error": str(exc)}

    async def _run_k8s_stress(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        """Apply one of the container-lab K8s Job manifests."""
        import subprocess

        kind = profile.executor_args.get("kind", "cpu-stress")
        manifest_map = {
            "cpu-stress": "/app/services/container-lab/k8s/cpu-stress.yaml",
            "memory-stress": "/app/services/container-lab/k8s/memory-stress.yaml",
            "disk-stress": "/app/services/container-lab/k8s/disk-stress.yaml",
        }
        manifest = manifest_map.get(kind, manifest_map["cpu-stress"])
        env = {
            "RUN_ID": run.run_id,
            "TARGET_NAMESPACE": profile.executor_args.get("target_namespace", "octo-shop-prod"),
            "TARGET_POD_LABEL": profile.executor_args.get("target_pod_label", "app=octo-drone-shop"),
            "DURATION_SECONDS": str(run.duration_seconds),
            "CPU_LOAD_PERCENT": str(profile.executor_args.get("cpu_load_percent", 80)),
            "ALLOCATE_MB": str(profile.executor_args.get("allocate_mb", 1024)),
        }
        try:
            rendered = subprocess.run(
                ["envsubst"],
                stdin=open(manifest, "r"),  # noqa: SIM115
                capture_output=True,
                text=True,
                env={**os.environ, **env},
            ).stdout
            apply = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=rendered,
                capture_output=True,
                text=True,
            )
            return {
                "status": "launched" if apply.returncode == 0 else "dispatch_error",
                "endpoint": "k8s-stress",
                "manifest": manifest,
                "resource": f"job/{kind}-{run.run_id}",
            }
        except FileNotFoundError as exc:
            return {"status": "dispatch_error", "error": str(exc)}

    async def _run_vm_stress(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        """SSH to the lab VM and run apply-stress.sh. Requires
        ``OCTO_VM_LAB_SSH_TARGET`` env to be set (e.g. ``ubuntu@host``)."""
        import subprocess

        target = os.getenv("OCTO_VM_LAB_SSH_TARGET", "")
        if not target:
            return {"status": "dispatch_error", "error": "OCTO_VM_LAB_SSH_TARGET not configured"}

        kind = profile.executor_args.get("kind", "cpu")
        cmd = (
            f"sudo RUN_ID={run.run_id} KIND={kind} "
            f"DURATION_SECONDS={run.duration_seconds} "
            f"/opt/octo/services/vm-lab/scripts/apply-stress.sh"
        )
        try:
            proc = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", target, cmd],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {
                "status": "launched" if proc.returncode == 0 else "dispatch_error",
                "endpoint": "vm-ssh",
                "target": target,
                "ssh_rc": proc.returncode,
            }
        except FileNotFoundError as exc:
            return {"status": "dispatch_error", "error": str(exc)}

    async def _run_edge_fuzz(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        """Launch octo-edge-fuzz as a subprocess. When the
        load-control pod does not have the edge-fuzz binary on PATH
        (typical single-image deploy), fall back to a stub response
        so the plan/run still completes."""
        import shutil
        import subprocess

        if not shutil.which("octo-edge-fuzz"):
            return {
                "status": "dispatch_error",
                "endpoint": "edge-fuzz",
                "error": "octo-edge-fuzz not on PATH — install services/edge-fuzz/ package into the same image",
            }

        target = profile.executor_args.get("target_url") or os.getenv("OCTO_EDGE_TARGET", "https://api.drone.octodemo.cloud")
        args = [
            "octo-edge-fuzz",
            "--target", target,
            "--endpoint", profile.executor_args.get("target_endpoint", "/api/admin/chaos/apply"),
            "--count", str(profile.executor_args.get("bad_tokens", 500)),
            "--run-id", run.run_id,
        ]
        try:
            # Fire-and-forget; fuzzer is short-lived.
            subprocess.Popen(args, env=os.environ)
            return {"status": "launched", "endpoint": "edge-fuzz", "target": target}
        except Exception as exc:
            return {"status": "dispatch_error", "error": str(exc)}

    async def _run_traffic_generator(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        headers = {"X-Run-Id": run.run_id}
        payload = {
            "run_id": run.run_id,
            "profile": profile.name.value,
            "duration_seconds": run.duration_seconds,
            **profile.executor_args,
        }
        try:
            resp = await self._traffic.post("/control/start", json=payload, headers=headers)
            return {"status": "launched", "http_status": resp.status_code, "endpoint": "traffic-generator"}
        except Exception as exc:  # pragma: no cover
            logger.warning("traffic generator dispatch failed: %s", exc)
            return {"status": "dispatch_error", "error": str(exc)}

    async def _run_chaos_admin(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        headers = {"X-Run-Id": run.run_id}
        payload = {
            "profile": profile.executor_args.get("chaos_profile", profile.name.value),
            "duration_seconds": run.duration_seconds,
            "intensity": profile.executor_args.get("intensity", "moderate"),
        }
        try:
            resp = await self._chaos.post("/api/admin/chaos/apply", json=payload, headers=headers)
            return {"status": "launched", "http_status": resp.status_code, "endpoint": "chaos-admin"}
        except Exception as exc:  # pragma: no cover
            logger.warning("chaos admin dispatch failed: %s", exc)
            return {"status": "dispatch_error", "error": str(exc)}


async def wait_then_mark_complete(run: Run, ledger, executor: ExecutorBackend, profile: Profile) -> None:
    """Sleep for ``run.duration_seconds`` then mark the run succeeded
    and persist. Exceptions → FAILED. Executed as a background task."""
    from .runs import _now_iso  # local to avoid cycle

    try:
        await asyncio.sleep(run.duration_seconds)
        run.state = RunState.SUCCEEDED
        run.completed_at = _now_iso()
    except asyncio.CancelledError:
        run.state = RunState.CANCELLED
        run.completed_at = _now_iso()
        raise
    except Exception as exc:  # pragma: no cover — defensive
        run.state = RunState.FAILED
        run.error = str(exc)
        run.completed_at = _now_iso()
    finally:
        ledger.update(run)
