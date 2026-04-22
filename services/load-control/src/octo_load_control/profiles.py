"""The 12 named workload profiles from OCI 360 §Load Profile Catalog.

Each profile is **declarative** — it describes what to launch, not how.
The executor (runs.py) interprets this spec and dispatches to the
right underlying service (traffic-generator, chaos admin, browser
runner, etc.).

Adding a profile is a data change (new entry in PROFILES), not a code
change.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class ProfileName(str, enum.Enum):
    """Canonical profile names — must match the OCI 360 spec §Load Profile Catalog."""

    DB_READ_BURST = "db-read-burst"
    DB_WRITE_BURST = "db-write-burst"
    WEB_CHECKOUT_SURGE = "web-checkout-surge"
    CRM_BACKOFFICE_SURGE = "crm-backoffice-surge"
    BROWSER_JOURNEY = "browser-journey"
    APP_EXCEPTION_STORM = "app-exception-storm"
    CACHE_MISS_STORM = "cache-miss-storm"
    STREAM_LAG_BURST = "stream-lag-burst"
    CONTAINER_CPU_PRESSURE = "container-cpu-pressure"
    CONTAINER_MEMORY_PRESSURE = "container-memory-pressure"
    VM_CPU_IO_PRESSURE = "vm-cpu-io-pressure"
    EDGE_AUTH_FAILURE_BURST = "edge-auth-failure-burst"


class ExecutorKind(str, enum.Enum):
    """Which backing service interprets the profile."""

    TRAFFIC_GENERATOR = "traffic-generator"
    CHAOS_ADMIN = "chaos-admin"            # CRM /api/admin/chaos/apply
    BROWSER_RUNNER = "browser-runner"      # Phase 4
    K8S_STRESS = "k8s-stress"              # stress job in the cluster
    VM_STRESS = "vm-stress"                # stress pod on a dedicated VM
    EDGE_FUZZ = "edge-fuzz"                # curl loop against API Gateway with bad auth


@dataclass(frozen=True)
class Profile:
    name: ProfileName
    description: str
    target_type: str              # db | web | crm | browser | app | cache | stream | container | vm | edge
    target_name: str              # e.g. atp, drone.octodemo.cloud
    executor: ExecutorKind
    executor_args: dict[str, Any] = field(default_factory=dict)
    expected_signals: tuple[str, ...] = field(default_factory=tuple)
    rollback_action: str = ""
    default_duration_seconds: int = 300

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "description": self.description,
            "target_type": self.target_type,
            "target_name": self.target_name,
            "executor": self.executor.value,
            "executor_args": dict(self.executor_args),
            "expected_signals": list(self.expected_signals),
            "rollback_action": self.rollback_action,
            "default_duration_seconds": self.default_duration_seconds,
        }


PROFILES: dict[ProfileName, Profile] = {
    # ── DB profiles ──────────────────────────────────────────────────
    ProfileName.DB_READ_BURST: Profile(
        name=ProfileName.DB_READ_BURST,
        description="High-frequency read load with SQL drill-down.",
        target_type="db",
        target_name="atp",
        executor=ExecutorKind.TRAFFIC_GENERATOR,
        executor_args={
            "target_rps": 20.0,
            "failure_injection_rate": 0.0,
            "paths": ["/api/products", "/api/products?category=drones"],
        },
        expected_signals=("apm.db.span.count ↑", "opsi.top_sql_by_reads ↑"),
        rollback_action="stop the traffic generator job",
    ),
    ProfileName.DB_WRITE_BURST: Profile(
        name=ProfileName.DB_WRITE_BURST,
        description="Insert/update bursts for redo + wait + commit visibility.",
        target_type="db",
        target_name="atp",
        executor=ExecutorKind.TRAFFIC_GENERATOR,
        executor_args={
            "target_rps": 10.0,
            "p_add_to_cart": 1.0,
            "p_checkout_given_cart": 1.0,
            "failure_injection_rate": 0.0,
        },
        expected_signals=("apm.db.writes ↑", "opsi.top_sql_by_elapsed_time ↑"),
        rollback_action="stop the traffic generator job",
    ),

    # ── Web + CRM ────────────────────────────────────────────────────
    ProfileName.WEB_CHECKOUT_SURGE: Profile(
        name=ProfileName.WEB_CHECKOUT_SURGE,
        description="End-to-end storefront + CRM order path under load.",
        target_type="web",
        target_name="drone.octodemo.cloud",
        executor=ExecutorKind.TRAFFIC_GENERATOR,
        executor_args={"target_rps": 30.0, "burst_multiplier": 2.0},
        expected_signals=(
            "apm.checkout.latency p95 ↑",
            "shop.checkout.count ↑",
            "crm.order_sync.count ↑",
        ),
        rollback_action="stop the traffic generator job",
    ),
    ProfileName.CRM_BACKOFFICE_SURGE: Profile(
        name=ProfileName.CRM_BACKOFFICE_SURGE,
        description="Operator-heavy workload on admin modules.",
        target_type="crm",
        target_name="backend.octodemo.cloud",
        executor=ExecutorKind.TRAFFIC_GENERATOR,
        executor_args={
            "target_base_url": "https://backend.octodemo.cloud",
            "target_rps": 5.0,
            "paths": ["/api/customers", "/api/tickets", "/api/products"],
        },
        expected_signals=("crm.admin.latency ↑", "apm.http_server_duration ↑"),
        rollback_action="stop the traffic generator job",
    ),

    # ── Browser + app exception ──────────────────────────────────────
    ProfileName.BROWSER_JOURNEY: Profile(
        name=ProfileName.BROWSER_JOURNEY,
        description="Real page navigation, cart, checkout, error + retry paths.",
        target_type="browser",
        target_name="drone.octodemo.cloud",
        executor=ExecutorKind.BROWSER_RUNNER,
        executor_args={"journey": "catalog-to-checkout", "iterations": 5},
        expected_signals=(
            "rum.session.count ↑",
            "rum.custom_event 'shop.checkout_complete' ↑",
        ),
        rollback_action="browser runner exits after iterations complete",
    ),
    ProfileName.APP_EXCEPTION_STORM: Profile(
        name=ProfileName.APP_EXCEPTION_STORM,
        description="Error-rate + trace + alert validation.",
        target_type="app",
        target_name="drone.octodemo.cloud",
        executor=ExecutorKind.TRAFFIC_GENERATOR,
        executor_args={"target_rps": 5.0, "failure_injection_rate": 0.9},
        expected_signals=("shop.http.errors_5xx ↑", "alarm 'error-rate' FIRING"),
        rollback_action="stop the traffic generator job",
    ),

    # ── Cache + stream ───────────────────────────────────────────────
    ProfileName.CACHE_MISS_STORM: Profile(
        name=ProfileName.CACHE_MISS_STORM,
        description="Cache cold-start + failover visibility.",
        target_type="cache",
        target_name="octo-cache",
        executor=ExecutorKind.TRAFFIC_GENERATOR,
        executor_args={
            "target_rps": 10.0,
            "bypass_cache_header": "X-Cache-Bypass=1",
        },
        expected_signals=("cache.hit_ratio ↓", "apm.cache.miss.count ↑"),
        rollback_action="stop the traffic generator job",
    ),
    ProfileName.STREAM_LAG_BURST: Profile(
        name=ProfileName.STREAM_LAG_BURST,
        description="Consumer delay, backlog, and redelivery.",
        target_type="stream",
        target_name="octo-event-stream",
        executor=ExecutorKind.K8S_STRESS,
        executor_args={"kind": "stream-producer-burst", "rps": 1000},
        expected_signals=("stream.consumer.lag ↑", "worker.job.retries ↑"),
        rollback_action="delete the stress job",
    ),

    # ── Container + VM ───────────────────────────────────────────────
    ProfileName.CONTAINER_CPU_PRESSURE: Profile(
        name=ProfileName.CONTAINER_CPU_PRESSURE,
        description="CPU throttling + HPA / alarm response.",
        target_type="container",
        target_name="octo-shop-prod/octo-drone-shop",
        executor=ExecutorKind.K8S_STRESS,
        executor_args={
            "kind": "cpu-stress",
            "target_namespace": "octo-shop-prod",
            "target_pod_label": "app=octo-drone-shop",
        },
        expected_signals=(
            "container.cpu_utilisation ↑",
            "hpa.current_replicas ↑",
            "kubectl.throttling_events > 0",
        ),
        rollback_action="kubectl delete job cpu-stress",
    ),
    ProfileName.CONTAINER_MEMORY_PRESSURE: Profile(
        name=ProfileName.CONTAINER_MEMORY_PRESSURE,
        description="OOM, restart, degraded latency.",
        target_type="container",
        target_name="octo-shop-prod/octo-drone-shop",
        executor=ExecutorKind.K8S_STRESS,
        executor_args={
            "kind": "memory-stress",
            "target_namespace": "octo-shop-prod",
            "target_pod_label": "app=octo-drone-shop",
            "allocate_mb": 1024,
        },
        expected_signals=("pod.OOMKilled > 0", "pod.restart_count ↑"),
        rollback_action="kubectl delete job memory-stress",
    ),
    ProfileName.VM_CPU_IO_PRESSURE: Profile(
        name=ProfileName.VM_CPU_IO_PRESSURE,
        description="Host saturation, process slowdown, disk latency.",
        target_type="vm",
        target_name="octo-vm-lab",
        executor=ExecutorKind.VM_STRESS,
        executor_args={"cpu_load_percent": 80, "io_workers": 4},
        expected_signals=("host.cpu ↑", "management_agent.process_state ↑"),
        rollback_action="stress-ng --stop or kill PID",
    ),

    # ── Edge ─────────────────────────────────────────────────────────
    ProfileName.EDGE_AUTH_FAILURE_BURST: Profile(
        name=ProfileName.EDGE_AUTH_FAILURE_BURST,
        description="Edge rejection, auth noise, route protection.",
        target_type="edge",
        target_name="api-gateway",
        executor=ExecutorKind.EDGE_FUZZ,
        executor_args={"target_endpoint": "/api/admin/chaos/apply", "bad_tokens": 500},
        expected_signals=("api_gateway.4xx ↑", "waf.detected ↑"),
        rollback_action="(inherent — the burst has a bounded iteration count)",
    ),
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[ProfileName(name)]
    except ValueError as exc:
        raise KeyError(
            f"unknown profile '{name}'; valid options: "
            + ", ".join(p.value for p in ProfileName)
        ) from exc


def list_profiles() -> list[Profile]:
    return list(PROFILES.values())
