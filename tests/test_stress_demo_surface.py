"""Phase 7 Plan 01 + Plan 02 surface tests.

Manifest-string assertions covering:
- Shop HPA: maxReplicas=10, CPU 60, memory 70, External shop_request_rate, behavior block
- Java APM HPA: new HPA block in apm-java-demo/deployment.yaml
- Helm chart: RPS metric default-off, javaGateway autoscaling block, java-gateway-hpa.yaml,
  stressRunner top-level values block
- OTel SDK pin bumps (shop + crm requirements)
- OTel Java agent pin (services/apm-java-demo/pom.xml)
- LLMetry pin file (tools/llmetry/pin.txt)
- OBS-01..05 field-shape regression guard (logging_sdk + push_log)
- Plan 02: Cluster Autoscaler script + config JSON + prometheus-adapter values

Pattern: ROOT + read_text per tests/test_unified_deploy_surface.py:1-25.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


# ── Raw OKE manifest tests ───────────────────────────────────────────────


def test_shop_hpa_max_replicas_bumped_to_ten() -> None:
    shop = read_text("deploy/k8s/oke/shop/deployment.yaml")
    assert "maxReplicas: 10" in shop


def test_shop_hpa_cpu_target_lowered_to_60() -> None:
    shop = read_text("deploy/k8s/oke/shop/deployment.yaml")
    # CPU lowered to 60, memory lowered to 70 — both should appear in the
    # shop HPA block.
    assert "averageUtilization: 60" in shop
    assert "averageUtilization: 70" in shop


def test_shop_hpa_has_external_rps_metric() -> None:
    shop = read_text("deploy/k8s/oke/shop/deployment.yaml")
    assert "type: External" in shop
    assert "name: shop_request_rate" in shop
    assert "service: octo-drone-shop" in shop


def test_shop_hpa_has_behavior_block() -> None:
    shop = read_text("deploy/k8s/oke/shop/deployment.yaml")
    assert "behavior:" in shop
    assert "scaleUp:" in shop
    assert "scaleDown:" in shop
    assert "stabilizationWindowSeconds: 30" in shop
    assert "stabilizationWindowSeconds: 300" in shop


def test_java_hpa_block_added() -> None:
    java = read_text("deploy/k8s/oke/apm-java-demo/deployment.yaml")
    assert "kind: HorizontalPodAutoscaler" in java
    assert "name: octo-apm-java-demo" in java
    assert "maxReplicas: 6" in java


# ── Helm chart tests ─────────────────────────────────────────────────────


def test_helm_rps_metric_is_default_off() -> None:
    values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    # Look for `rps:` block followed by `enabled: false` (default OFF per D-05).
    match = re.search(
        r"rps:\s*\n\s*enabled:\s*false", values, re.MULTILINE
    )
    assert match is not None, "shop.autoscaling.rps.enabled must default to false"


def test_helm_java_gateway_autoscaling_block_present() -> None:
    values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    assert "javaGateway:" in values
    # Locate the javaGateway block and verify a nested autoscaling block with
    # maxReplicas: 6 lives inside it (not just anywhere in the file — crm has
    # its own maxReplicas: 6 that would otherwise mask this assertion).
    java_match = re.search(
        r"^javaGateway:\s*\n((?:[ \t]+.*\n|\n)+)", values, re.MULTILINE
    )
    assert java_match is not None, "javaGateway: top-level block must exist"
    java_block = java_match.group(1)
    assert "autoscaling:" in java_block, "javaGateway must have nested autoscaling block"
    assert "maxReplicas: 6" in java_block, "javaGateway.autoscaling.maxReplicas must be 6"


def test_helm_java_gateway_hpa_template_exists() -> None:
    template_path = ROOT / "deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml"
    assert template_path.exists(), "java-gateway-hpa.yaml template missing"
    content = template_path.read_text(encoding="utf-8")
    assert "{{- if and .Values.javaGateway.enabled .Values.javaGateway.autoscaling.enabled }}" in content


def test_helm_stress_runner_values_block_present() -> None:
    """Plan 07-01 is the sole owner of values.yaml — stressRunner block staged here
    so Plan 07-03 templates render without re-editing values.yaml."""
    values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    assert "stressRunner:" in values
    # Default off
    match = re.search(
        r"stressRunner:\s*\n(?:.*\n)*?\s*enabled:\s*false", values, re.MULTILINE
    )
    assert match is not None, "stressRunner.enabled must default to false"
    assert "namespace: octo-stress" in values


# ── D-21 dependency pin tests ────────────────────────────────────────────

_OTEL_SDK_MIN_FLOOR = (1, 27)


def _extract_otel_sdk_version(text: str) -> tuple[int, int, int] | None:
    """Parse `opentelemetry-sdk==X.Y[.Z]` from a requirements file."""
    match = re.search(r"opentelemetry-sdk==(\d+)\.(\d+)(?:\.(\d+))?", text)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch)


def test_otel_sdk_pinned_in_shop_requirements() -> None:
    text = read_text("shop/requirements.txt")
    assert "opentelemetry-sdk==" in text
    version = _extract_otel_sdk_version(text)
    assert version is not None, "could not parse opentelemetry-sdk version in shop/requirements.txt"
    assert version[:2] >= _OTEL_SDK_MIN_FLOOR, (
        f"shop opentelemetry-sdk version {version} is below floor {_OTEL_SDK_MIN_FLOOR}"
    )


def test_otel_sdk_pinned_in_crm_requirements() -> None:
    # Plan referenced `crm/server/requirements.txt`; the actual location in this
    # repo is `crm/requirements.txt` (Rule 3 — corrected to real path).
    text = read_text("crm/requirements.txt")
    assert "opentelemetry-sdk==" in text
    version = _extract_otel_sdk_version(text)
    assert version is not None, "could not parse opentelemetry-sdk version in crm/requirements.txt"
    assert version[:2] >= _OTEL_SDK_MIN_FLOOR, (
        f"crm opentelemetry-sdk version {version} is below floor {_OTEL_SDK_MIN_FLOOR}"
    )


def test_otel_java_agent_pinned_to_2_27() -> None:
    pom = read_text("services/apm-java-demo/pom.xml")
    assert "2.27.0" in pom


def test_llmetry_pin_bumped() -> None:
    pin_path = ROOT / "tools/llmetry/pin.txt"
    assert pin_path.exists(), "tools/llmetry/pin.txt missing"
    content = pin_path.read_text(encoding="utf-8").lower()
    assert "llmetry" in content
    # Must contain a version specifier (== or >= or pin-style version)
    assert re.search(r"(==|>=|~=|\d+\.\d+)", content) is not None


def test_obs_field_shape_regression_unbroken() -> None:
    """OBS-01..05 field-shape regression guard for D-21 pin bumps.

    The plan calls for either (a) running an existing OBS field-shape suite or
    (b) scaffolding a placeholder that proves the import path is unbroken.
    No existing OBS field-shape suite was discovered; this placeholder reads
    the canonical structured-logging source file and verifies the canonical
    `push_log` symbol and core OTel resource-attribute keys (service.name,
    trace_id, span_id) are still wired — substring assertions only so the
    test is offline-feasible and survives sys.path differences across
    test runners (top-level vs shop/ via shop/tests/conftest.py).
    """
    logging_sdk_src = read_text("shop/server/observability/logging_sdk.py")
    # Canonical entry point must remain — proves no API rename slipped in.
    assert "def push_log" in logging_sdk_src, "push_log function must exist"
    # Canonical OTel resource-attribute keys MUST stay present (OBS-01..05 field contract).
    # These are the join keys used by Log Analytics + APM correlation pivots.
    assert "trace_id" in logging_sdk_src, "trace_id field must remain in logging_sdk"
    assert "span_id" in logging_sdk_src, "span_id field must remain in logging_sdk"

    otel_setup_src = read_text("shop/server/observability/otel_setup.py")
    assert "service.name" in otel_setup_src or "SERVICE_NAME" in otel_setup_src, (
        "service.name resource attribute must remain in otel_setup"
    )

    # D-21 floor: pin bumps must leave the file importable as text — the file
    # must reference the canonical OTel API import (opentelemetry.sdk or trace).
    assert "opentelemetry" in otel_setup_src.lower(), (
        "otel_setup must still import from opentelemetry"
    )


# ── Plan 07-02: Cluster Autoscaler + prometheus-adapter surface ──────────


_CA_SCRIPT_RELATIVE = "deploy/oke/configure-cluster-autoscaler.sh"
_CA_CONFIG_RELATIVE = "deploy/oke/cluster-autoscaler-config.json"
_PROM_ADAPTER_VALUES_RELATIVE = (
    "deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml"
)


def test_configure_cluster_autoscaler_script_exists() -> None:
    """CA wrapper script must exist and be executable (D-04 operator handoff)."""
    script_path = ROOT / _CA_SCRIPT_RELATIVE
    assert script_path.exists(), f"{_CA_SCRIPT_RELATIVE} missing"
    assert os.access(script_path, os.X_OK), (
        f"{_CA_SCRIPT_RELATIVE} must be executable (chmod +x)"
    )


def test_configure_cluster_autoscaler_dry_run_default() -> None:
    """APPLY default is false — opposite of install-oci-kubernetes-monitoring.sh.

    Cluster Autoscaler is destructive to provision: a misconfigured pool can
    over-scale and burn quota. Default to dry-run; require explicit --apply.
    """
    body = read_text(_CA_SCRIPT_RELATIVE)
    assert ': "${APPLY:=false}"' in body, (
        "configure-cluster-autoscaler.sh must default APPLY to false (dry-run)"
    )


def test_configure_cluster_autoscaler_has_install_and_update_branches() -> None:
    """Idempotency contract: first run installs the add-on, re-runs update it."""
    body = read_text(_CA_SCRIPT_RELATIVE)
    assert "install-addon" in body, "script must invoke `oci ce cluster install-addon`"
    assert "update-addon" in body, "script must invoke `oci ce cluster update-addon`"


def test_configure_cluster_autoscaler_has_confirm_prompt() -> None:
    """D-04 interactive confirmation gate before mutating OCI state."""
    body = read_text(_CA_SCRIPT_RELATIVE)
    assert "read -p" in body, (
        "configure-cluster-autoscaler.sh must prompt the operator before --apply"
    )


def test_configure_cluster_autoscaler_has_list_addons_precheck() -> None:
    """Idempotency precheck via `oci ce cluster list-addons`."""
    body = read_text(_CA_SCRIPT_RELATIVE)
    assert "list-addons" in body, (
        "script must list existing add-ons to decide install vs update"
    )


def test_configure_cluster_autoscaler_reads_config_json() -> None:
    """Script consumes the sibling cluster-autoscaler-config.json file."""
    body = read_text(_CA_SCRIPT_RELATIVE)
    assert "cluster-autoscaler-config.json" in body, (
        "script must reference the sibling JSON config"
    )


def test_cluster_autoscaler_config_has_min_max_2_4() -> None:
    """CA config pins nodes 2:4:${OKE_NODE_POOL_OCID} envsubst placeholder.

    No live OCID is committed — the placeholder is resolved at apply time
    via envsubst with OKE_NODE_POOL_OCID supplied by the operator (SEC-04,
    KB-456).
    """
    config_path = ROOT / _CA_CONFIG_RELATIVE
    assert config_path.exists(), f"{_CA_CONFIG_RELATIVE} missing"
    body = config_path.read_text(encoding="utf-8")
    assert "2:4:" in body, "CA config must pin nodes to min=2:max=4"
    assert "${OKE_NODE_POOL_OCID}" in body, (
        "CA config must keep OKE_NODE_POOL_OCID as an envsubst placeholder"
    )
    # Must parse as JSON.
    parsed = json.loads(body)
    assert "configurations" in parsed or "addonConfigurations" in parsed or "nodes" in body, (
        "CA config must declare a configurations array (or nodes key)"
    )


def test_prometheus_adapter_values_publishes_shop_rps() -> None:
    """Adapter declares shop_request_rate + java_request_rate as External metrics.

    These metric names must match the HPA External-metric references in
    deploy/k8s/oke/shop/deployment.yaml and the Helm template gated by
    .Values.shop.autoscaling.rps.enabled. Namespace pin (octo_apm_demo)
    ensures we do not accidentally publish to a foreign label space.
    """
    values_path = ROOT / _PROM_ADAPTER_VALUES_RELATIVE
    assert values_path.exists(), f"{_PROM_ADAPTER_VALUES_RELATIVE} missing"
    body = values_path.read_text(encoding="utf-8")
    assert "shop_request_rate" in body, (
        "adapter values must publish shop_request_rate External metric"
    )
    assert "java_request_rate" in body, (
        "adapter values must publish java_request_rate External metric"
    )
    assert "external" in body.lower(), "adapter values must declare external rule list"
    assert "octo_apm_demo" in body, (
        "adapter values must pin the octo_apm_demo namespace"
    )


# ── Plan 07-03: stress-runner manifests + FastAPI wrapper + scenarios ────

import shutil
import subprocess  # noqa: E402

import pytest  # noqa: E402

_SR_NS_RELATIVE = "deploy/k8s/oke/stress-runner/namespace.yaml"
_SR_DEPLOY_RELATIVE = "deploy/k8s/oke/stress-runner/deployment.yaml"
_SR_SVC_RELATIVE = "deploy/k8s/oke/stress-runner/service.yaml"
_SR_RBAC_RELATIVE = "deploy/k8s/oke/stress-runner/rbac.yaml"
_SR_HELM_DEPLOY_RELATIVE = (
    "deploy/helm/octo-apm-demo/templates/stress-runner-deployment.yaml"
)
_SR_HELM_SVC_RELATIVE = (
    "deploy/helm/octo-apm-demo/templates/stress-runner-service.yaml"
)
_SR_HELM_RBAC_RELATIVE = (
    "deploy/helm/octo-apm-demo/templates/stress-runner-rbac.yaml"
)
_SR_WRAPPER_MAIN_RELATIVE = "tools/stress-runner/octo_stress_runner/main.py"
_SR_WRAPPER_INIT_RELATIVE = "tools/stress-runner/octo_stress_runner/__init__.py"
_SR_PYPROJECT_RELATIVE = "tools/stress-runner/pyproject.toml"
_SR_DOCKERFILE_RELATIVE = "tools/stress-runner/Dockerfile"
_SR_SCENARIOS = [
    "tools/stress-runner/scenarios/checkout_journey.js",
    "tools/stress-runner/scenarios/catalog_browse.js",
    "tools/stress-runner/scenarios/login_burst.js",
]


def test_stress_runner_namespace_manifest() -> None:
    """Namespace manifest exists and pins `octo-stress`."""
    body = read_text(_SR_NS_RELATIVE)
    assert "kind: Namespace" in body
    assert "name: octo-stress" in body


def test_stress_runner_deployment_manifest() -> None:
    """Deployment ships replicas=1 + 8080 + OTEL service name + pull secret."""
    body = read_text(_SR_DEPLOY_RELATIVE)
    assert "kind: Deployment" in body
    assert "name: octo-stress-runner" in body
    assert "replicas: 1" in body
    assert "containerPort: 8080" in body
    assert "OCTO_STRESS_RUNNER_INTERNAL_KEY" in body
    # OTEL_SERVICE_NAME literal followed (within a few lines) by octo-stress-runner.
    assert re.search(
        r"OTEL_SERVICE_NAME[\s\S]{0,80}octo-stress-runner", body
    ), "OTEL_SERVICE_NAME env must resolve to octo-stress-runner"
    assert "ocir-pull-secret" in body


def test_stress_runner_service_manifest() -> None:
    """Service is ClusterIP on 8080 with no Ingress reference."""
    body = read_text(_SR_SVC_RELATIVE)
    assert "kind: Service" in body
    assert "type: ClusterIP" in body
    assert "port: 8080" in body
    assert "kind: Ingress" not in body, (
        "stress-runner service must not declare an Ingress"
    )


def test_stress_runner_rbac_minimal() -> None:
    """ServiceAccount only — NO Role/RoleBinding/ClusterRoleBinding (pod
    does not call k8s API)."""
    body = read_text(_SR_RBAC_RELATIVE)
    assert "kind: ServiceAccount" in body
    assert "name: octo-stress-runner" in body
    assert "kind: Role" not in body, (
        "stress-runner rbac must not include a Role"
    )
    assert "kind: RoleBinding" not in body, (
        "stress-runner rbac must not include a RoleBinding"
    )
    assert "kind: ClusterRoleBinding" not in body, (
        "stress-runner rbac must not include a ClusterRoleBinding"
    )


def _helm_template(extra_args: list[str]) -> str:
    """Run helm template; skip the test if helm is unavailable (offline runs)."""
    if shutil.which("helm") is None:
        pytest.skip("helm CLI not installed; skipping template render test")
    cmd = [
        "helm",
        "template",
        "deploy/helm/octo-apm-demo",
        "--set",
        "global.image.tenancy=tenant",
        *extra_args,
    ]
    result = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


def test_stress_runner_helm_template_default_off() -> None:
    """Default helm render must NOT contain stress-runner Deployment."""
    rendered = _helm_template([])
    # Crucially, the Deployment is absent — there may still be the values
    # block name commented somewhere, so we check the actual resource.
    assert "name: octo-stress-runner" not in rendered, (
        "default helm render must not include octo-stress-runner (D-05)"
    )


def test_stress_runner_helm_template_enabled_on() -> None:
    """`--set stressRunner.enabled=true` renders the Deployment."""
    rendered = _helm_template(["--set", "stressRunner.enabled=true"])
    assert "name: octo-stress-runner" in rendered, (
        "helm render with stressRunner.enabled=true must include "
        "octo-stress-runner Deployment"
    )


def test_stress_runner_wrapper_main_concurrency_lock() -> None:
    """Wrapper enforces concurrency=1 → HTTP 409 (D-14)."""
    body = read_text(_SR_WRAPPER_MAIN_RELATIVE)
    assert ("asyncio.Lock" in body) or ("_active_run" in body) or (
        "_active" in body
    ), "wrapper must declare an asyncio.Lock or _active guard"
    assert "409" in body, "wrapper must return HTTP 409 on concurrent run attempt"


def test_stress_runner_wrapper_sigterm_path() -> None:
    """Wrapper sends SIGTERM to active k6 subprocess on /internal/clear."""
    body = read_text(_SR_WRAPPER_MAIN_RELATIVE)
    assert "signal.SIGTERM" in body or "SIGTERM" in body, (
        "wrapper must reference signal.SIGTERM for graceful drain"
    )
    assert ("send_signal" in body) or (".terminate(" in body), (
        "wrapper must send SIGTERM via send_signal or process.terminate()"
    )


def test_stress_runner_wrapper_internal_key_header() -> None:
    """Wrapper validates the X-Internal-Service-Key header (D-12)."""
    body = read_text(_SR_WRAPPER_MAIN_RELATIVE)
    assert "X-Internal-Service-Key" in body, (
        "wrapper must validate X-Internal-Service-Key header"
    )


def test_stress_runner_wrapper_otel_service_name() -> None:
    """Wrapper reads OTEL_SERVICE_NAME from env (separate APM entity)."""
    body = read_text(_SR_WRAPPER_MAIN_RELATIVE)
    assert "OTEL_SERVICE_NAME" in body, (
        "wrapper must reference OTEL_SERVICE_NAME for APM entity binding"
    )


def test_stress_runner_scenarios_have_required_headers() -> None:
    """Every k6 scenario sets X-Octo-Stress-Target, X-Run-Id, and the wrapper
    invokes k6 with experimental-opentelemetry output."""
    for rel in _SR_SCENARIOS:
        body = read_text(rel)
        assert "X-Octo-Stress-Target" in body, (
            f"{rel} must send X-Octo-Stress-Target header (D-09 LB pin)"
        )
        assert "X-Run-Id" in body, (
            f"{rel} must propagate X-Run-Id header for APM correlation"
        )
    wrapper_body = read_text(_SR_WRAPPER_MAIN_RELATIVE)
    assert "experimental-opentelemetry" in wrapper_body, (
        "wrapper must invoke k6 with --out experimental-opentelemetry "
        "for native OTLP export (D-06)"
    )


def test_stress_runner_scenarios_target_lb_host() -> None:
    """Scenarios drive an env-driven base URL — no hardcoded host."""
    for rel in _SR_SCENARIOS:
        body = read_text(rel)
        assert "STRESS_TARGET_URL" in body, (
            f"{rel} must read base URL from __ENV.STRESS_TARGET_URL"
        )


def test_stress_runner_internal_run_returns_202() -> None:
    """POST /internal/run returns HTTP 202 (UI-SPEC `Run starting`)."""
    body = read_text(_SR_WRAPPER_MAIN_RELATIVE)
    # Either a status_code=202 / HTTP_202_ACCEPTED on the decorator OR
    # an explicit response status_code=202.
    assert (
        "HTTP_202_ACCEPTED" in body
        or "status_code=202" in body
        or "status_code = 202" in body
    ), "wrapper /internal/run must declare HTTP 202 on success"


def test_stress_runner_pyproject_exists() -> None:
    """pyproject.toml declares fastapi + uvicorn + pydantic deps."""
    body = read_text(_SR_PYPROJECT_RELATIVE)
    body_lower = body.lower()
    assert "fastapi" in body_lower, "pyproject must depend on fastapi"
    assert "uvicorn" in body_lower, "pyproject must depend on uvicorn"
    assert "pydantic" in body_lower, "pyproject must depend on pydantic"


def test_stress_runner_dockerfile_uses_k6_image() -> None:
    """Dockerfile multi-stages from grafana/k6 to inherit the k6 binary."""
    body = read_text(_SR_DOCKERFILE_RELATIVE)
    assert "grafana/k6" in body, (
        "Dockerfile must reference grafana/k6 image (multi-stage k6 binary copy)"
    )


def test_plan_07_03_does_not_edit_values_yaml() -> None:
    """Single-writer guard: Plan 07-01 owns values.yaml; the
    `stressRunner:` top-level key appears EXACTLY once. A re-edit by Plan
    07-03 would either create a duplicate top-level key or drift the
    block — both would fail this assertion."""
    body = read_text("deploy/helm/octo-apm-demo/values.yaml")
    # Match top-level key only (start of line + no leading space).
    matches = re.findall(r"^stressRunner:\s*$", body, re.MULTILINE)
    assert len(matches) == 1, (
        f"`stressRunner:` top-level key must appear exactly once in values.yaml "
        f"(found {len(matches)}). Plan 07-01 is the sole writer."
    )


# ── Plan 07-07: APM saved queries surface ────────────────────────────────

_APM_SQ_DIR = "tools/apm-saved-queries"
_APM_SQ_FILES = {
    "pod_count": f"{_APM_SQ_DIR}/oke-pod-count-over-time.json",
    "latency": f"{_APM_SQ_DIR}/oke-latency-percentiles-during-scale.json",
    "trace_new_pods": f"{_APM_SQ_DIR}/oke-trace-propagation-new-pods.json",
    "error_sat": f"{_APM_SQ_DIR}/oke-error-saturation-slow-spans.json",
}
_APM_SQ_NAMESPACE_PATTERNS = ("octo_apm_demo", "octo-apm-demo")
_APM_SQ_DRILLDOWN_HOSTS = (
    "lm.octodemo.cloud",
    "phoenix.octodemo.cloud",
    "openlit.octodemo.cloud",
    "grafana.octodemo.cloud",
)


def _load_apm_saved_query(key: str) -> dict:
    return json.loads(read_text(_APM_SQ_FILES[key]))


def _has_namespace_filter(text: str) -> bool:
    return any(p in text for p in _APM_SQ_NAMESPACE_PATTERNS)


def test_apm_saved_queries_directory_exists() -> None:
    """tools/apm-saved-queries/ exists with README.md."""
    assert (ROOT / _APM_SQ_DIR).is_dir(), (
        f"{_APM_SQ_DIR}/ must exist"
    )
    assert (ROOT / _APM_SQ_DIR / "README.md").is_file(), (
        f"{_APM_SQ_DIR}/README.md must exist"
    )


def test_apm_saved_query_pod_count_valid() -> None:
    """oke-pod-count-over-time.json parses + has required fields/filters."""
    spec = _load_apm_saved_query("pod_count")
    for field in ("name", "displayName", "queryString"):
        assert field in spec, f"pod-count saved query missing field: {field}"
    query = spec["queryString"]
    assert "k8s.pod.name" in query, (
        "pod-count query must reference k8s.pod.name"
    )
    assert _has_namespace_filter(query), (
        "pod-count query must scope to octo_apm_demo namespace"
    )
    # 1min bucket (allow `1m`, `1min`, `bucket(1min)`, etc.).
    assert ("1min" in query) or ("1m" in query), (
        "pod-count query must bucket by 1m / 1min"
    )


def test_apm_saved_query_latency_percentiles_valid() -> None:
    """oke-latency-percentiles-during-scale.json has p50/p95/p99 + checkout."""
    spec = _load_apm_saved_query("latency")
    query = spec["queryString"]
    for pct in ("p50", "p95", "p99"):
        assert pct in query, f"latency query must contain {pct}"
    assert "/api/shop/checkout" in query, (
        "latency query must filter on /api/shop/checkout operation"
    )
    assert "30s" in query, (
        "latency query must bucket by 30s"
    )
    assert _has_namespace_filter(query), (
        "latency query must scope to octo_apm_demo namespace"
    )


def test_apm_saved_query_trace_to_new_pods_valid() -> None:
    """oke-trace-propagation-new-pods.json filters on k8s.pod.name + window."""
    spec = _load_apm_saved_query("trace_new_pods")
    query = spec["queryString"]
    assert "k8s.pod.name" in query, (
        "trace-to-new-pods query must filter on k8s.pod.name"
    )
    assert _has_namespace_filter(query), (
        "trace-to-new-pods query must scope to octo_apm_demo namespace"
    )
    # First-appearance window logic — accept any of these signal tokens.
    assert any(tok in query for tok in ("baseline_pod_set", "not in", "first_appear", "new_pod")), (
        "trace-to-new-pods query must express first-appearance window logic"
    )


def test_apm_saved_query_error_saturation_valid() -> None:
    """oke-error-saturation-slow-spans.json filters on span.status + top-N."""
    spec = _load_apm_saved_query("error_sat")
    query = spec["queryString"]
    assert "span.status" in query, (
        "error-saturation query must filter on span.status"
    )
    assert _has_namespace_filter(query), (
        "error-saturation query must scope to octo_apm_demo namespace"
    )
    # top-N pattern: head limit or head N.
    assert "head" in query, (
        "error-saturation query must use a top-N (head) pattern"
    )


def test_apm_saved_queries_drilldown_links_present() -> None:
    """At least one saved query carries the D-20 external drilldown hosts."""
    seen: set[str] = set()
    for key in _APM_SQ_FILES:
        body = read_text(_APM_SQ_FILES[key])
        for host in _APM_SQ_DRILLDOWN_HOSTS:
            if host in body:
                seen.add(host)
    missing = set(_APM_SQ_DRILLDOWN_HOSTS) - seen
    assert not missing, (
        f"Saved-query JSON files must collectively reference all D-20 drilldown "
        f"hosts; missing: {sorted(missing)}"
    )


def test_apm_saved_queries_apply_script_dry_run_default() -> None:
    """apply.sh exists, is executable, dry-run default, confirm prompt."""
    apply_path = ROOT / _APM_SQ_DIR / "apply.sh"
    assert apply_path.is_file(), f"{_APM_SQ_DIR}/apply.sh must exist"
    assert os.access(apply_path, os.X_OK), (
        f"{_APM_SQ_DIR}/apply.sh must be executable"
    )
    body = apply_path.read_text(encoding="utf-8")
    assert ': "${APPLY:=false}"' in body, (
        "apply.sh must default APPLY=false (dry-run by default)"
    )
    assert "read -p" in body or "read -r -p" in body, (
        "apply.sh must contain a confirm prompt before mutating"
    )


def test_apm_saved_queries_no_live_ocids() -> None:
    """Grep the directory for live OCIDs — must be empty."""
    pattern = re.compile(r"ocid1\.")
    apm_dir = ROOT / _APM_SQ_DIR
    if not apm_dir.is_dir():
        # Directory may not yet exist in RED state; failure is expected
        # via the directory-exists test above.
        return
    offenders: list[str] = []
    for entry in apm_dir.rglob("*"):
        if entry.is_file():
            try:
                content = entry.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if pattern.search(content):
                offenders.append(str(entry.relative_to(ROOT)))
    assert not offenders, (
        f"Live OCIDs leaked in apm-saved-queries: {offenders}"
    )


# ── Plan 07-08: OCI Monitoring alarms ───────────────────────────────────

_MON_ALARM_DIR = "tools/monitoring-alarms"
_HIGH_CPU_ALARM = f"{_MON_ALARM_DIR}/octo-high-cpu-saturation.json"
_HPA_MAX_ALARM = f"{_MON_ALARM_DIR}/octo-hpa-at-max-replicas.json"


def test_monitoring_alarms_directory_exists() -> None:
    """Directory + README ship together."""
    alarm_dir = ROOT / _MON_ALARM_DIR
    assert alarm_dir.is_dir(), f"{_MON_ALARM_DIR}/ must exist"
    assert (alarm_dir / "README.md").is_file(), (
        f"{_MON_ALARM_DIR}/README.md must exist"
    )


def test_high_cpu_alarm_valid() -> None:
    """High CPU saturation alarm parses and uses octo_apm_demo namespace."""
    path = ROOT / _HIGH_CPU_ALARM
    assert path.is_file(), f"{_HIGH_CPU_ALARM} must exist"
    spec = json.loads(path.read_text(encoding="utf-8"))
    assert spec["namespace"] == "octo_apm_demo", (
        "alarm must target octo_apm_demo namespace (OBS-05)"
    )
    query = spec.get("query", "")
    assert "shop_cpu_saturation_pct" in query, (
        "alarm query must reference D-17 shop_cpu_saturation_pct metric"
    )
    assert "> 80" in query or ">80" in query, (
        "alarm threshold must be > 80 (D-18 #1)"
    )
    assert spec.get("pendingDuration") == "PT2M", (
        "pendingDuration must be PT2M (2 minutes, D-18 #1)"
    )


def test_hpa_max_replicas_alarm_valid() -> None:
    """HPA-at-max-replicas alarm parses and references max-replicas threshold."""
    path = ROOT / _HPA_MAX_ALARM
    assert path.is_file(), f"{_HPA_MAX_ALARM} must exist"
    spec = json.loads(path.read_text(encoding="utf-8"))
    assert spec["namespace"] == "octo_apm_demo", (
        "alarm must target octo_apm_demo namespace (OBS-05)"
    )
    query = spec.get("query", "")
    assert "shop_pod_count" in query, (
        "alarm query must reference D-17 shop_pod_count metric"
    )
    # Threshold should be the maxReplicas value (10 per D-03)
    assert "10" in query, (
        "alarm threshold must reference maxReplicas value (10)"
    )
    assert spec.get("pendingDuration") == "PT5M", (
        "pendingDuration must be PT5M (5 minutes, D-18 #2)"
    )


def test_monitoring_alarms_apply_script_dry_run_default() -> None:
    """apply.sh exists, executable, dry-run default, confirm prompt."""
    apply_path = ROOT / _MON_ALARM_DIR / "apply.sh"
    assert apply_path.is_file(), f"{_MON_ALARM_DIR}/apply.sh must exist"
    assert os.access(apply_path, os.X_OK), (
        f"{_MON_ALARM_DIR}/apply.sh must be executable"
    )
    body = apply_path.read_text(encoding="utf-8")
    assert ': "${APPLY:=false}"' in body, (
        "apply.sh must default APPLY=false (dry-run by default)"
    )
    assert "read -p" in body or "read -r -p" in body, (
        "apply.sh must contain a confirm prompt before mutating"
    )


def test_monitoring_alarms_use_envsubst_for_ocids() -> None:
    """Alarm JSONs use envsubst placeholders for COMPARTMENT_ID and topic OCID."""
    for path_rel in (_HIGH_CPU_ALARM, _HPA_MAX_ALARM):
        path = ROOT / path_rel
        if not path.is_file():
            continue  # surfaced by *_alarm_valid tests
        content = path.read_text(encoding="utf-8")
        assert "${COMPARTMENT_ID}" in content, (
            f"{path_rel} must reference ${{COMPARTMENT_ID}} placeholder"
        )
        assert "${NOTIFICATION_TOPIC_OCID}" in content, (
            f"{path_rel} must reference ${{NOTIFICATION_TOPIC_OCID}} placeholder"
        )


def test_monitoring_alarms_no_live_ocids() -> None:
    """Grep the monitoring-alarms directory for live OCIDs — must be empty."""
    pattern = re.compile(r"ocid1\.")
    alarm_dir = ROOT / _MON_ALARM_DIR
    if not alarm_dir.is_dir():
        return
    offenders: list[str] = []
    for entry in alarm_dir.rglob("*"):
        if entry.is_file():
            try:
                content = entry.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if pattern.search(content):
                offenders.append(str(entry.relative_to(ROOT)))
    assert not offenders, (
        f"Live OCIDs leaked in monitoring-alarms: {offenders}"
    )


def test_hpa_max_replicas_value_matches_helm_values() -> None:
    """Cross-file invariant: alarm threshold == shop.autoscaling.maxReplicas."""
    path = ROOT / _HPA_MAX_ALARM
    if not path.is_file():
        return
    spec = json.loads(path.read_text(encoding="utf-8"))
    helm_values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    # Shop block ships maxReplicas: 10 — alarm threshold must match
    assert "maxReplicas: 10" in helm_values, (
        "shop.autoscaling.maxReplicas changed in values.yaml; update alarm threshold"
    )
    query = spec.get("query", "")
    assert "10" in query, (
        "alarm threshold (10) must match shop.autoscaling.maxReplicas in values.yaml"
    )


# ── Plan 09: Log Analytics saved searches + dashboard for OKE autoscaling ───

_LA_SAVED_SEARCH_DIR = "tools/la-saved-searches"
_LA_HPA = f"{_LA_SAVED_SEARCH_DIR}/oke-autoscaling-hpa-events.json"
_LA_CA = f"{_LA_SAVED_SEARCH_DIR}/oke-autoscaling-ca-events.json"
_LA_KUBELET = f"{_LA_SAVED_SEARCH_DIR}/oke-autoscaling-kubelet-pressure.json"
_LA_STRESS_AUDIT = f"{_LA_SAVED_SEARCH_DIR}/oke-autoscaling-stress-audit.json"
_LA_DASHBOARD = f"{_LA_SAVED_SEARCH_DIR}/oke-autoscaling-dashboard.json"


def _load_la_json(rel: str) -> dict:
    return json.loads(read_text(rel))


def test_la_oke_hpa_events_search() -> None:
    spec = _load_la_json(_LA_HPA)
    query = spec.get("queryString", "")
    assert "hpa-controller" in query, (
        "HPA saved-search must filter on Subsystem='hpa-controller'"
    )
    assert "Kubernetes Logs" in query, (
        "HPA saved-search must scope to 'Kubernetes Logs' Log Source"
    )


def test_la_oke_ca_events_search() -> None:
    spec = _load_la_json(_LA_CA)
    query = spec.get("queryString", "")
    assert "cluster-autoscaler" in query, (
        "Cluster Autoscaler saved-search must filter on the "
        "'cluster-autoscaler' add-on subsystem"
    )


def test_la_oke_kubelet_pressure_search() -> None:
    spec = _load_la_json(_LA_KUBELET)
    query = spec.get("queryString", "")
    for symptom in ("NodeNotReady", "ImagePullBackOff", "OOMKilled"):
        assert symptom in query, (
            f"kubelet pressure saved-search must match '{symptom}'"
        )


def test_la_oke_stress_audit_search() -> None:
    spec = _load_la_json(_LA_STRESS_AUDIT)
    query = spec.get("queryString", "")
    assert "run_id" in query, (
        "stress audit saved-search must reference 'run_id' (cross-channel "
        "pivot key with phase 7 plan 05 audit log lines)"
    )
    assert "run_id is not null" in query, (
        "stress audit saved-search must filter where run_id is not null"
    )


def test_la_oke_dashboard_links_four_searches() -> None:
    raw = read_text(_LA_DASHBOARD)
    spec = json.loads(raw)
    # Dashboard must declare the "OKE Autoscaling Timeline" display name
    # somewhere in its top-level metadata.
    display_name = spec.get("displayName", "")
    assert "OKE Autoscaling Timeline" in display_name, (
        "dashboard must use displayName 'OKE Autoscaling Timeline'"
    )
    # Dashboard JSON must reference all four saved-search names so that
    # apply.sh + manual import lands a coherent set.
    for ss_name in (
        "oke-autoscaling-hpa-events",
        "oke-autoscaling-ca-events",
        "oke-autoscaling-kubelet-pressure",
        "oke-autoscaling-stress-audit",
    ):
        assert ss_name in raw, (
            f"dashboard JSON must reference saved-search '{ss_name}'"
        )


def test_la_oke_searches_no_live_ocids() -> None:
    ocid_re = re.compile(r"ocid1\.")
    ipv4_re = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
    offenders: list[str] = []
    for rel in (
        _LA_HPA, _LA_CA, _LA_KUBELET, _LA_STRESS_AUDIT, _LA_DASHBOARD,
    ):
        content = read_text(rel)
        if ocid_re.search(content) or ipv4_re.search(content):
            offenders.append(rel)
    assert not offenders, (
        f"Live OCIDs or IPs leaked in LA saved searches: {offenders}"
    )


def test_la_apply_sh_unchanged() -> None:
    """apply.sh auto-discovers *.json — no plan-09 edits should land in it.

    Soft check: the 'oke-autoscaling' substring must NOT appear hardcoded
    in apply.sh. Auto-discovery is the contract.
    """
    apply_sh = read_text(f"{_LA_SAVED_SEARCH_DIR}/apply.sh")
    assert "oke-autoscaling" not in apply_sh, (
        "apply.sh must remain generic — saved searches are discovered by "
        "glob, not hardcoded by name"
    )


# ── Plan 07-05: /api/admin/stress/* surface + three-channel MELTS audit ─────
#
# 17 tests pin the contract for `crm/server/modules/stress_test.py` and its
# wiring (admin.py role list, main.py router include, oci_monitoring helper,
# page route nav_key). Tests 1-13 use FastAPI TestClient with the
# stress-runner cross-pod call mocked via httpx.MockTransport. Tests 14-17
# are source-text assertions (file existence + literal substrings).
#
# Pattern: mirrors crm/tests/test_admin_coordinator.py for TestClient setup
# (session injector middleware) and the existing _SR_* substring tests above
# for source-grep style assertions.

import sys as _sys  # noqa: E402

_CRM_ROOT = ROOT / "crm"
if str(_CRM_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_CRM_ROOT))


def _build_stress_client(
    user: dict | None = None,
    runner_responses: dict | None = None,
):
    """Build a TestClient over a FastAPI app with the stress_test router mounted.

    `runner_responses` maps a stress-runner internal path (e.g.
    "/internal/run") to a tuple ``(status_code, json_body)`` that the mocked
    httpx client will return when the stress_test handler calls out to the
    runner pod. Default responses are 200 + ``{}`` for state/clear and
    202 + ``{run_id, status}`` echoed for /internal/run.
    """
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from server.modules import stress_test  # local import for clarity

    runner_responses = runner_responses or {}

    def _runner_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in runner_responses:
            code, body = runner_responses[path]
            return httpx.Response(code, json=body)
        # Sensible defaults so the unit tests do not have to spell out every
        # downstream response shape.
        if path == "/internal/run":
            payload = {}
            try:
                import json as _json

                payload = _json.loads(request.content.decode("utf-8") or "{}")
            except Exception:
                payload = {}
            return httpx.Response(
                202,
                json={
                    "run_id": payload.get("run_id", "00000000-0000-0000-0000-000000000000"),
                    "status": "started",
                },
            )
        if path == "/internal/clear":
            return httpx.Response(200, json={"status": "stopped"})
        if path == "/internal/state":
            return httpx.Response(200, json={"status": "idle"})
        return httpx.Response(404, json={"error": "not_mocked", "path": path})

    transport = httpx.MockTransport(_runner_handler)

    # Patch httpx.AsyncClient to use the MockTransport by default in this test.
    _original_async_client = httpx.AsyncClient

    class _PatchedAsyncClient(_original_async_client):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("transport", transport)
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _PatchedAsyncClient  # type: ignore[misc]

    app = FastAPI()

    if user is not None:
        async def _session_injector(request: Request, call_next):
            request.state.current_user = user
            return await call_next(request)

        app.middleware("http")(_session_injector)

    app.include_router(stress_test.router)
    if hasattr(stress_test, "page_router"):
        app.include_router(stress_test.page_router)

    client = TestClient(app)
    # Stash a teardown hook on the client for callers that need to restore httpx.
    client._restore_httpx = lambda: setattr(  # type: ignore[attr-defined]
        httpx, "AsyncClient", _original_async_client
    )
    return client


def _admin_user() -> dict:
    return {"user_id": 1, "username": "admin", "role": "admin"}


def _non_admin_user() -> dict:
    return {"user_id": 2, "username": "viewer", "role": "viewer"}


def _valid_apply_body() -> dict:
    return {
        "scenario": "checkout_journey",
        "target_service": "shop",
        "rps": 25,
        "duration_seconds": 60,
        "note": "demo run",
    }


def _set_stress_runner_env(monkeypatch) -> None:
    """The stress_test module reads cfg.octo_stress_runner_internal_key at
    request time; ensure it is non-empty so the handler does not short-circuit
    on a missing-key check (separate from the admin/host gates under test)."""
    import os as _os

    _os.environ.setdefault("OCTO_STRESS_RUNNER_INTERNAL_KEY", "test-internal-key")
    _os.environ.setdefault(
        "OCTO_STRESS_RUNNER_BASE_URL",
        "http://octo-stress-runner.octo-stress.svc.cluster.local:8080",
    )


# Tests 1-13 — endpoint behavior contract --------------------------------


def test_stress_apply_returns_202_with_run_id(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        response = client.post(
            "/api/admin/stress/apply",
            json=_valid_apply_body(),
        )
        assert response.status_code == 202, response.text
        body = response.json()
        assert "run_id" in body
        # UUID format check (8-4-4-4-12 hex)
        assert re.match(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
            body["run_id"],
        ), f"run_id is not a UUID: {body['run_id']}"
        assert body.get("status") == "started"
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_apply_rejects_non_admin_host_403(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        response = client.post(
            "/api/admin/stress/apply",
            headers={"host": "evil.example.com"},
            json=_valid_apply_body(),
        )
        assert response.status_code == 403, response.text
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_apply_rejects_missing_octo_scope_403(monkeypatch) -> None:
    """target_service must be 'shop' — anything else returns 422 (Pydantic)
    or 403 (scope guard). Either is acceptable per the plan."""
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        body = _valid_apply_body()
        body["target_service"] = "crm"  # not in the allow-list
        response = client.post("/api/admin/stress/apply", json=body)
        assert response.status_code in (403, 422), response.text
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_apply_concurrency_returns_409(monkeypatch) -> None:
    """A 409 from the stress-runner pod (concurrency=1 enforced there) must
    propagate through the CRM admin handler as a 409 with the active run_id."""
    _set_stress_runner_env(monkeypatch)
    runner_responses = {
        "/internal/run": (
            409,
            {"status": "active", "active_run_id": "11111111-2222-3333-4444-555555555555"},
        ),
    }
    client = _build_stress_client(user=_admin_user(), runner_responses=runner_responses)
    try:
        response = client.post("/api/admin/stress/apply", json=_valid_apply_body())
        assert response.status_code == 409, response.text
        body = response.json()
        # Body should surface the active run_id from the runner's reply.
        flat = (response.text or "").lower()
        assert "active_run_id" in flat or "11111111" in flat or "active_run_id" in str(body).lower()
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_apply_rejects_rps_out_of_range_422(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        body = _valid_apply_body()
        body["rps"] = 201  # > 200 cap (D-13)
        response = client.post("/api/admin/stress/apply", json=body)
        assert response.status_code == 422, response.text
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_apply_rejects_duration_out_of_range_422(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        body = _valid_apply_body()
        body["duration_seconds"] = 601  # > 600 cap (D-13)
        response = client.post("/api/admin/stress/apply", json=body)
        assert response.status_code == 422, response.text
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_apply_rejects_unknown_target_422(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        body = _valid_apply_body()
        body["scenario"] = "ddos"  # not in {checkout_journey, catalog_browse, login_burst}
        response = client.post("/api/admin/stress/apply", json=body)
        assert response.status_code == 422, response.text
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_clear_sends_sigterm_and_emits_audit(monkeypatch) -> None:
    """POST /api/admin/stress/clear must:
       1) reach the runner /internal/clear endpoint,
       2) emit a push_log row with status='stopped',
       3) call oci_monitoring.increment_stress_run(..., status='stopped').
    """
    _set_stress_runner_env(monkeypatch)
    pushed: list[tuple] = []
    counter_calls: list[tuple] = []

    runner_responses = {
        # Mark a run as active in the runner's view so /clear is meaningful.
        "/internal/state": (
            200,
            {
                "status": "running",
                "run_id": "77777777-aaaa-bbbb-cccc-dddddddddddd",
                "scenario": "checkout_journey",
                "rps": 25,
                "duration_seconds": 60,
                "target_host": "https://shop.example.test",
                "started_at": 0,
            },
        ),
        "/internal/clear": (200, {"status": "stopped"}),
    }
    client = _build_stress_client(user=_admin_user(), runner_responses=runner_responses)

    # Monkeypatch the audit sinks the handler is expected to call.
    from server.modules import stress_test as _st  # type: ignore

    def _fake_push_log(level, message, **fields):
        pushed.append((level, message, fields))

    def _fake_increment_stress_run(run_id, status):
        counter_calls.append((run_id, status))

    monkeypatch.setattr(_st, "push_log", _fake_push_log, raising=False)
    monkeypatch.setattr(
        _st, "increment_stress_run", _fake_increment_stress_run, raising=False
    )

    try:
        response = client.post("/api/admin/stress/clear")
        assert response.status_code == 200, response.text
        # At least one push_log row tagged status=stopped
        stopped_logs = [
            row for row in pushed if row[2].get("status") == "stopped"
        ]
        assert stopped_logs, (
            f"expected a push_log call with status=stopped; got {pushed}"
        )
        # At least one counter increment with status=stopped
        assert any(c[1] == "stopped" for c in counter_calls), (
            f"expected increment_stress_run(..., status='stopped'); got {counter_calls}"
        )
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_clear_idempotent_when_idle(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    runner_responses = {
        "/internal/state": (200, {"status": "idle"}),
        "/internal/clear": (200, {"status": "idle"}),
    }
    client = _build_stress_client(user=_admin_user(), runner_responses=runner_responses)
    try:
        response = client.post("/api/admin/stress/clear")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("status") == "idle"
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_state_returns_active_when_running(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    runner_responses = {
        "/internal/state": (
            200,
            {
                "status": "running",
                "run_id": "abcd1234-1111-2222-3333-444455556666",
                "scenario": "checkout_journey",
                "rps": 25,
                "duration_seconds": 60,
                "target_host": "https://shop.example.test",
                "started_at": 1700000000,
            },
        ),
    }
    client = _build_stress_client(user=_admin_user(), runner_responses=runner_responses)
    try:
        response = client.get("/api/admin/stress/state")
        assert response.status_code == 200, response.text
        body = response.json()
        for required in (
            "run_id",
            "scenario",
            "rps",
            "duration_seconds",
            "target_host",
            "started_at",
            "status",
        ):
            assert required in body, f"state missing field: {required}"
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_state_returns_idle_when_no_run(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    runner_responses = {"/internal/state": (200, {"status": "idle"})}
    client = _build_stress_client(user=_admin_user(), runner_responses=runner_responses)
    try:
        response = client.get("/api/admin/stress/state")
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "idle"}
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_presets_returns_three_bundles(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        response = client.get("/api/admin/stress/presets")
        assert response.status_code == 200, response.text
        body = response.json()
        # Accept either a bare list or a {presets: [...]} envelope.
        presets = body if isinstance(body, list) else body.get("presets", [])
        assert len(presets) == 3, f"expected 3 presets, got {len(presets)}: {body}"
        names = sorted([(p.get("name") or p.get("id") or "").lower() for p in presets])
        assert names == ["heavy", "light", "medium"], names
        for p in presets:
            assert "rps" in p
            assert "duration_seconds" in p
            assert "scenario" in p
            assert 1 <= int(p["rps"]) <= 200
            assert 10 <= int(p["duration_seconds"]) <= 600
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


def test_stress_page_route_returns_html_with_csp_nonce(monkeypatch) -> None:
    _set_stress_runner_env(monkeypatch)
    client = _build_stress_client(user=_admin_user())
    try:
        # CSP nonce middleware is not active in this isolated test app; the
        # page handler should still render and the template should reference
        # csp_nonce. We allow either: (a) the rendered response contains the
        # `nonce=` HTML attribute (full template wired), OR (b) the source of
        # the page handler references `csp_nonce` in the template context.
        response = client.get("/admin/stress-test")
        # Treat 200 as the must-have; if templates are missing in the test
        # harness, accept 500 only if the source-side nav_key check (test 17)
        # would still pass — but the contract here is 200 + nonce attr.
        assert response.status_code == 200, response.text
        ctype = response.headers.get("content-type", "")
        assert "text/html" in ctype, ctype
        # Best-effort nonce check; the chaos analog uses `nonce="{{ csp_nonce }}"`.
        assert "nonce=" in response.text or "csp_nonce" in response.text
    finally:
        client._restore_httpx()  # type: ignore[attr-defined]


# Tests 14-17 — source-text assertions (no app boot required) ------------


def test_admin_module_includes_stress_operator_role_guard() -> None:
    body = read_text("crm/server/modules/admin.py")
    assert "stress-operator" in body, (
        "crm/server/modules/admin.py must add 'stress-operator' to _ALLOWED_ROLES (D-12)"
    )


def test_main_includes_stress_admin_router() -> None:
    body = read_text("crm/server/main.py")
    assert "from server.modules.stress_test import" in body, (
        "main.py must import the stress_test router(s) (parallel to chaos)"
    )
    assert "stress_admin_router" in body, (
        "main.py must alias the import as stress_admin_router (or include it)"
    )
    assert "app.include_router(stress_admin_router)" in body, (
        "main.py must mount stress_admin_router"
    )


def test_oci_monitoring_increment_stress_run_helper_emits_namespace_point() -> None:
    body = read_text("shop/server/observability/oci_monitoring.py")
    assert "def increment_stress_run" in body, (
        "oci_monitoring.py must expose increment_stress_run(run_id, status)"
    )
    # The helper must publish to the octo_apm_demo namespace via _point or
    # an equivalent ingestion call.
    assert "stress_run_count" in body, (
        "increment_stress_run must publish a 'stress_run_count' metric (D-17)"
    )
    assert "octo_apm_demo" in body, (
        "oci_monitoring.py must publish to the 'octo_apm_demo' namespace"
    )


def test_stress_page_route_passes_nav_key() -> None:
    body = read_text("crm/server/modules/stress_test.py")
    # Literal substring assertion: the page-route handler must include
    # nav_key="stress" in the template context so Plan 07-06's base.html nav
    # entry can render with the active state.
    assert 'nav_key="stress"' in body or "nav_key='stress'" in body, (
        "stress_test.py page-route handler must pass nav_key='stress' to "
        "templates.TemplateResponse(...) (Plan 07-06 base.html consumer)"
    )


# ── Plan 07-06: stress_test_admin.html template + base.html nav ──────────


_STRESS_TEMPLATE_REL = "crm/server/templates/stress_test_admin.html"
_BASE_TEMPLATE_REL = "crm/server/templates/base.html"


def test_stress_template_exists() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert '{% extends "base.html" %}' in body, (
        "stress_test_admin.html must extend base.html (UI-SPEC §Existing System Reuse)"
    )


def test_stress_template_has_nonced_script() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    # Exactly one CSP-nonced inline <script> tag (no external src=).
    nonced = body.count('<script nonce="{{ csp_nonce }}">')
    assert nonced == 1, (
        f"stress_test_admin.html must contain exactly one inline "
        f'<script nonce="{{{{ csp_nonce }}}}">, found {nonced}'
    )


def test_stress_template_form_fields_present() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    for label in (
        "Scenario",
        "Target service",
        "Requests per second (1–200)",
        "Duration (seconds, 10–600)",
        "Run note (who / why)",
    ):
        assert label in body, f"stress_test_admin.html missing form label: {label!r}"


def test_stress_template_primary_cta_copy() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert "Apply stress run" in body, (
        "Primary CTA copy must be verbatim 'Apply stress run' (UI-SPEC §Copywriting Contract)"
    )


def test_stress_template_destructive_cta_copy() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert "Stop active run" in body, (
        "Destructive CTA copy must be verbatim 'Stop active run' (UI-SPEC §Copywriting Contract)"
    )


def test_stress_template_confirm_on_stop() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    # The confirm() dialog must reference 'Stop run' from the UI-SPEC
    # destructive confirmation copy and live inside the inline script.
    script_start = body.find("<script nonce=")
    script_end = body.find("</script>", script_start)
    assert script_start != -1 and script_end != -1, (
        "stress_test_admin.html missing inline <script>...</script> block"
    )
    script_block = body[script_start:script_end]
    assert "confirm(" in script_block, (
        "Stop button must call confirm() before DELETE (UI-SPEC §Destructive confirmation)"
    )
    assert "Stop run" in script_block, (
        "confirm() copy must include 'Stop run' (UI-SPEC §Destructive confirmation)"
    )


def test_stress_template_polling_cadence() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert "2000" in body, (
        "stress_test_admin.html must contain 2000 (2s active-run polling cadence)"
    )
    assert "10000" in body, (
        "stress_test_admin.html must contain 10000 (10s idle polling cadence)"
    )


def test_stress_template_aria_live_audit() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    # The audit/state <pre> must be screen-reader live.
    assert 'role="status"' in body, (
        "audit <pre> must have role=\"status\" (UI-SPEC §Keyboard / a11y)"
    )
    assert 'aria-live="polite"' in body, (
        "audit <pre> must have aria-live=\"polite\" (UI-SPEC §Keyboard / a11y)"
    )


def test_stress_template_audit_banner_copy() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert "Admin only — every action is audited" in body, (
        "Audit banner copy must be verbatim from UI-SPEC §Audit banner"
    )


def test_stress_template_fetches_stress_endpoints() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    for endpoint in (
        "/api/admin/stress/presets",
        "/api/admin/stress/state",
        "/api/admin/stress/apply",
        "/api/admin/stress/clear",
    ):
        assert endpoint in body, (
            f"stress_test_admin.html inline script must fetch {endpoint}"
        )


def test_stress_template_no_external_script_tags() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert "<script src=" not in body, (
        "stress_test_admin.html must not include external <script src=...> "
        "(CSP discipline + UI-SPEC §Registry Safety)"
    )


def test_stress_template_no_internal_wording() -> None:
    # Forbidden internal wording must not appear in operator-facing prose.
    # We tolerate the words inside <pre>...</pre> (audit JSON) and inside
    # <script>...</script> (JS payloads referencing audit-event names).
    body = read_text(_STRESS_TEMPLATE_REL)
    forbidden = ("Workflow Gateway", "Coordinator", "k6 wrapper")
    in_pre = False
    in_script = False
    for raw_line in body.splitlines():
        line = raw_line
        if "<pre" in line:
            in_pre = True
        if "<script" in line:
            in_script = True
        if not (in_pre or in_script):
            for term in forbidden:
                assert term not in line, (
                    f"Forbidden internal wording {term!r} appears in operator-facing "
                    f"prose: {line!r} (UI-SPEC §Forbidden copy)"
                )
        if "</pre>" in line:
            in_pre = False
        if "</script>" in line:
            in_script = False


def test_stress_template_no_live_ocids() -> None:
    body = read_text(_STRESS_TEMPLATE_REL)
    assert not re.search(r"ocid1\.", body), (
        "stress_test_admin.html must not contain live OCIDs (UI-SPEC §Forbidden copy)"
    )


def test_base_html_has_stress_test_nav_li() -> None:
    body = read_text(_BASE_TEMPLATE_REL)
    assert '<a href="/admin/stress-test"' in body, (
        "base.html sidebar must include an <a href=\"/admin/stress-test\"> link "
        "(UI-SPEC §Asset Inventory)"
    )
    assert "Stress Test" in body, (
        "base.html sidebar must include the visible label 'Stress Test'"
    )


# ── Plan 07-10: Workshop Lab 11 + LB routing runbook + mkdocs nav ──────────


_LAB11_REL = "site/workshop/lab-11-oke-autoscaling.md"
_LB_ROUTING_REL = "site/operations/stress-demo-lb-routing.md"
_MKDOCS_REL = "mkdocs.yml"


def test_lab11_file_exists() -> None:
    path = ROOT / _LAB11_REL
    assert path.exists(), (
        f"{_LAB11_REL} must exist — workshop Lab 11 closes the Phase 7 narrative (D-22)"
    )


def test_lab11_cross_links_labs() -> None:
    body = read_text(_LAB11_REL)
    # D-22 mandates cross-links to Labs 01 / 05 / 09.
    assert "lab-01" in body, "Lab 11 must cross-link Lab 01 (first trace pattern, D-22)"
    assert "lab-05" in body, "Lab 11 must cross-link Lab 05 (metric+alarm pattern, D-22)"
    assert "lab-09" in body, "Lab 11 must cross-link Lab 09 (run_id pivot pattern, D-22)"


def test_lab11_includes_drilldown_hosts() -> None:
    body = read_text(_LAB11_REL)
    # D-20: all four external drilldown hosts must appear as outbound links.
    for host in (
        "lm.octodemo.cloud",
        "phoenix.octodemo.cloud",
        "openlit.octodemo.cloud",
        "grafana.octodemo.cloud",
    ):
        assert host in body, (
            f"Lab 11 must include drilldown link block for {host} (D-20)"
        )


def test_lab11_walks_full_arc() -> None:
    body = read_text(_LAB11_REL)
    lower = body.lower()
    # D-22 — the seven walking-tour stops.
    for marker in (
        "baseline",
        "trigger",
        "hpa",
        "cluster autoscaler",
        "alarm",
        "drill",
        "cool-down",
    ):
        assert marker in lower, (
            f"Lab 11 must walk through {marker!r} (D-22 seven-step arc)"
        )


def test_lab11_admin_path_referenced() -> None:
    body = read_text(_LAB11_REL)
    assert "/admin/stress-test" in body, (
        "Lab 11 must reference /admin/stress-test (the admin page from plan 07-06)"
    )


def test_lab11_run_id_pivot_pattern() -> None:
    body = read_text(_LAB11_REL)
    assert "run_id" in body, (
        "Lab 11 must reference run_id as the cross-channel pivot key (D-22)"
    )


def test_lb_routing_runbook_exists() -> None:
    path = ROOT / _LB_ROUTING_REL
    assert path.exists(), (
        f"{_LB_ROUTING_REL} must exist — operator runbook for the D-09 header-routing rule"
    )
    body = read_text(_LB_ROUTING_REL)
    assert "X-Octo-Stress-Target" in body, (
        "LB routing runbook must document the X-Octo-Stress-Target header (D-09)"
    )
    assert "oci lb routing-policy" in body, (
        "LB routing runbook must document the `oci lb routing-policy` CLI calls"
    )


def test_lb_routing_runbook_no_live_ocids() -> None:
    body = read_text(_LB_ROUTING_REL)
    assert not re.search(r"ocid1\.", body), (
        f"{_LB_ROUTING_REL} must not contain live OCIDs (SEC-04, T-07-44)"
    )
    assert not re.search(r"(\d{1,3}\.){3}\d{1,3}", body), (
        f"{_LB_ROUTING_REL} must not contain live IPv4 addresses (SEC-04, T-07-44)"
    )


def test_mkdocs_nav_includes_lab11() -> None:
    body = read_text(_MKDOCS_REL)
    assert "lab-11-oke-autoscaling.md" in body, (
        "mkdocs.yml nav must include the new Lab 11 entry"
    )


def test_mkdocs_nav_includes_runbook() -> None:
    body = read_text(_MKDOCS_REL)
    assert "stress-demo-lb-routing.md" in body, (
        "mkdocs.yml nav must include the LB routing operator runbook"
    )


def test_unified_deploy_surface_stress_runner_check() -> None:
    body = read_text("tests/test_unified_deploy_surface.py")
    # The unified-surface test file must include a function that asserts the
    # stress-runner manifest exists — PATTERNS.md §tests/test_unified_deploy_surface.py (EDIT).
    assert "stress-runner" in body, (
        "tests/test_unified_deploy_surface.py must include a stress-runner manifest check"
    )
    assert "octo-stress-runner" in body, (
        "tests/test_unified_deploy_surface.py must assert octo-stress-runner is in the manifest"
    )


def test_unified_deploy_surface_ca_script_check() -> None:
    body = read_text("tests/test_unified_deploy_surface.py")
    # Same file must include the CA-script presence + executable + install-addon check.
    assert "configure-cluster-autoscaler.sh" in body, (
        "tests/test_unified_deploy_surface.py must include a configure-cluster-autoscaler.sh check"
    )
    assert "install-addon" in body, (
        "tests/test_unified_deploy_surface.py must assert install-addon is in the CA script"
    )
    assert "os.access" in body, (
        "tests/test_unified_deploy_surface.py must assert the CA script is executable"
    )
