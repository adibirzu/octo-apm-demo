# Phase 7: OKE Autoscaling and Stress Demo - Pattern Map

**Mapped:** 2026-05-18
**Files analyzed:** 24 new/modified files
**Analogs found:** 22 / 24 (2 no-analog)

> Pattern mapping for Phase 7 SCALE-01..04. Every new artifact lands on top of a
> proven existing analog. Two artifacts (prometheus-adapter values, k6 wrapper
> Dockerfile/image) have no direct in-repo analog and must follow RESEARCH.md.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crm/server/templates/stress_test_admin.html` | template | request-response | `crm/server/templates/chaos_admin.html` | **exact** |
| `crm/server/modules/stress_test.py` | controller (router) + service | request-response | `crm/server/chaos/admin.py` | **exact** |
| `crm/server/modules/admin.py` (EDIT) | controller (role list) | request-response | `crm/server/modules/admin.py:20` | **self-edit** |
| `crm/server/main.py` (EDIT) | wiring | startup | `crm/server/main.py:217-220` | **self-edit** |
| `crm/server/templates/base.html` (EDIT) | template (nav) | startup-render | `crm/server/templates/base.html:67-86` | **self-edit** |
| `deploy/k8s/oke/shop/deployment.yaml` (EDIT) | manifest (HPA) | declarative | `deploy/k8s/oke/shop/deployment.yaml:370-394` | **self-edit** |
| `deploy/k8s/oke/apm-java-demo/deployment.yaml` (EDIT) | manifest (HPA add) | declarative | `deploy/k8s/oke/shop/deployment.yaml:370-394` | role-match |
| `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml` (EDIT) | helm template (HPA) | declarative | `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml:1-29` | **self-edit** |
| `deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml` | helm template (HPA) | declarative | `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml` | **exact** |
| `deploy/helm/octo-apm-demo/values.yaml` (EDIT) | helm values | declarative | `deploy/helm/octo-apm-demo/values.yaml:120-125,196-199` | **self-edit** |
| `deploy/k8s/oke/stress-runner/namespace.yaml` | manifest (namespace) | declarative | `tools/traffic-generator/k8s/deployment.yaml:8-15` | **exact** |
| `deploy/k8s/oke/stress-runner/deployment.yaml` | manifest (deployment) | declarative | `tools/traffic-generator/k8s/deployment.yaml:18-80` | **exact** |
| `deploy/k8s/oke/stress-runner/service.yaml` | manifest (service) | declarative | `deploy/helm/octo-apm-demo/templates/shop-service.yaml` | role-match |
| `deploy/k8s/oke/stress-runner/rbac.yaml` | manifest (RBAC) | declarative | (none in repo) | **no analog** |
| `deploy/helm/octo-apm-demo/templates/stress-runner-deployment.yaml` | helm template | declarative | `deploy/helm/octo-apm-demo/templates/shop-deployment.yaml` | role-match |
| `deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml` | helm values (sub-chart) | declarative | (none) — RESEARCH.md Pattern 1 | **no analog** |
| `deploy/oke/configure-cluster-autoscaler.sh` | script (OCI control plane) | request-response | `deploy/oke/install-oci-kubernetes-monitoring.sh` | role-match |
| `deploy/oke/cluster-autoscaler-config.json` | config (declarative) | declarative | (none) — RESEARCH.md Pattern 2 | spec-driven |
| `tools/stress-runner/octo_stress_runner/main.py` | service (FastAPI wrapper) | request-response | `crm/server/chaos/admin.py` (router skeleton) + RESEARCH.md Pattern 3 | role-match |
| `tools/stress-runner/scenarios/*.js` | k6 scenarios | streaming (HTTP load) | `shop/k6/checkout-load.js`, `crm/k6/stress_test.js` | **exact** |
| `shop/server/observability/oci_monitoring.py` (EDIT) | service (metric publish) | event-driven (periodic push) | `shop/server/observability/oci_monitoring.py:136-181` | **self-edit** |
| `tools/la-saved-searches/oke-autoscaling-*.json` (×4) | config (saved searches) | declarative | `tools/la-saved-searches/errors-by-route.json` + `apply.sh` | **exact** |
| `site/workshop/lab-11-oke-autoscaling.md` | docs | static-render | `site/workshop/lab-09-chaos-drill.md`, `lab-05-metric-and-alarm.md` | **exact** |
| `site/operations/stress-demo-lb-routing.md` | docs (runbook) | static-render | `site/operations/chaos.md` | role-match |
| `tests/test_stress_demo_surface.py` | test | unit + manifest assertions | `tests/test_unified_deploy_surface.py` | **exact** |
| `tests/test_unified_deploy_surface.py` (EDIT) | test (extend) | unit | `tests/test_unified_deploy_surface.py:27-80` | **self-edit** |

---

## Pattern Assignments

### `crm/server/templates/stress_test_admin.html` (template, request-response)

**Analog:** `crm/server/templates/chaos_admin.html` (lines 1-97). The phase explicitly clones this template per D-11 and UI-SPEC §Asset Inventory.

**Layout pattern** (chaos_admin.html lines 1-47):
```html
{% extends "base.html" %}

{% block content %}
<div class="page">
    <header class="page-header">
        <h1>Chaos Control</h1>
        <p class="page-subtitle">
            Restricted to the <code>chaos-operator</code> role. Scenarios
            apply to the Shop, the CRM, or both, for a bounded TTL.
            Everything here is audited.
        </p>
    </header>

    <section id="current-state" class="card">
        <h2>Currently active</h2>
        <pre id="current-state-json">Loading…</pre>
        <button type="button" id="btn-clear" class="btn btn-danger">Clear scenario</button>
    </section>

    <section class="card">
        <h2>Apply a preset</h2>
        <form id="apply-form">
            <label>
                Preset
                <select id="scenario-id" name="scenario_id" required></select>
            </label>
            ...
            <button type="submit" class="btn btn-primary">Apply</button>
        </form>
        <pre id="apply-result"></pre>
    </section>
</div>
```

**Copy verbatim:** `{% extends "base.html" %}`, the `.page > .page-header > .card > form` structure, the `<pre id="...">` audit/result panes, and the two action buttons (`.btn-primary` + `.btn-danger`).

**Adapt for Phase 7 per UI-SPEC §Copywriting Contract:** Title `OKE stress test`; subtitle mentions `admin role (optional stress-operator scope)`, hard caps, audit; form fields = Scenario / Target service / RPS / Duration / Note; CTA = `Apply stress run`; danger CTA = `Stop active run` with `confirm()` per UI-SPEC §Destructive confirmation.

**Inline JS pattern** (chaos_admin.html lines 49-95):
```html
<script nonce="{{ csp_nonce }}">
(function () {
    const presetSelect = document.getElementById('scenario-id');
    const currentEl = document.getElementById('current-state-json');
    const applyResult = document.getElementById('apply-result');

    async function refresh() {
        const [presetsRes, stateRes] = await Promise.all([
            fetch('/api/admin/chaos/presets'),
            fetch('/api/admin/chaos/state'),
        ]);
        ...
    }

    document.getElementById('apply-form').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const data = new FormData(ev.target);
        const body = { ... };
        const res = await fetch('/api/admin/chaos/apply', { method: 'POST', ... });
        applyResult.textContent = JSON.stringify(await res.json(), null, 2);
        refresh();
    });
    ...
    refresh();
})();
</script>
```

**Adapt:** Rewrite the three fetches to `/api/admin/stress/{presets,apply,clear,state}`. Add `window.setInterval(refresh, active ? 2000 : 10000)` per UI-SPEC §Polling. Wrap the stop click in `if (!confirm(...)) return;` per UI-SPEC §Destructive confirmation. Use the same `nonce="{{ csp_nonce }}"` CSP-nonced inline-script pattern — do NOT introduce external JS.

---

### `crm/server/modules/stress_test.py` (controller + service, request-response)

**Analog:** `crm/server/chaos/admin.py` (full file, 266 lines). This is the canonical "audited, role-gated, admin-only, TTL-bounded operator surface" — D-11/D-12 mirror it directly.

**Imports pattern** (chaos/admin.py lines 19-38, with coordinator additions for host-bound):
```python
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from server.security.auth_deps import require_role
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
```

Plus from `crm/server/modules/coordinator.py` (lines 14-20) for host-bound + admin user:
```python
from server.modules._authz import require_admin_user
from server.config import cfg
```

**Router declaration with role guard** (chaos/admin.py lines 40-48):
```python
logger = logging.getLogger("chaos.audit")

CHAOS_ADMIN_ROLE = os.getenv("CHAOS_ADMIN_ROLE", "chaos-operator").strip().lower() or "chaos-operator"

router = APIRouter(
    prefix="/api/admin/chaos",
    tags=["chaos-admin"],
    dependencies=[require_role(CHAOS_ADMIN_ROLE)],
)
```

**Adapt:** prefix `/api/admin/stress`, env `STRESS_ADMIN_ROLE` defaulting to `stress-operator`, tag `stress-admin`.

**Pydantic request model with hard caps** (chaos/admin.py lines 66-78):
```python
class ApplyRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    target: str = Field(default="both")
    ttl_seconds: int = Field(default=300, ge=10, le=MAX_TTL_SECONDS)
    note: str | None = Field(default=None, max_length=512)

    @field_validator("target")
    @classmethod
    def _valid_target(cls, v: str) -> str:
        norm = v.strip().lower()
        if norm not in {"shop", "crm", "both"}:
            raise ValueError("target must be shop|crm|both")
        return norm
```

**Adapt for D-13 caps:**
```python
class ApplyRequest(BaseModel):
    scenario: str = Field(pattern=r"^(checkout_journey|catalog_browse|login_burst)$")
    target_service: str = Field(default="shop")
    rps: int = Field(default=25, ge=1, le=200)
    duration_seconds: int = Field(default=60, ge=10, le=600)
    note: str | None = Field(default=None, max_length=512)

    @field_validator("target_service")
    @classmethod
    def _shop_only(cls, v: str) -> str:
        if v.strip().lower() != "shop":
            raise ValueError("target_service must be 'shop' for v1.1")
        return "shop"
```

**Endpoint shape** (chaos/admin.py lines 160-219):
```python
@router.get("/presets")
def list_presets() -> dict[str, Any]: ...

@router.get("/state")
def read_state() -> dict[str, Any]: ...

@router.post("/apply", status_code=status.HTTP_201_CREATED)
def apply_scenario(payload: ApplyRequest, request: Request) -> dict[str, Any]: ...

@router.post("/clear")
def clear_scenario(request: Request) -> dict[str, bool]: ...
```

**Adapt:** Same four-endpoint surface. `/apply` returns HTTP 202 per UI-SPEC `Run starting (HTTP 202)`. Concurrency=1 returns HTTP 409 per D-14. Hard timeout `duration + 30s` per D-14 wired via an asyncio task (RESEARCH Pattern 3).

**HTML page router pattern** (chaos/admin.py lines 226-262):
```python
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_PAGE_ROUTER = APIRouter(
    prefix="/admin",
    tags=["chaos-admin"],
    dependencies=[require_role(CHAOS_ADMIN_ROLE)],
)

@_PAGE_ROUTER.get("/chaos", response_class=HTMLResponse)
def chaos_admin_page(request: Request) -> HTMLResponse:
    templates = _get_templates()
    nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(
        request,
        "chaos_admin.html",
        {
            "title": "Chaos Control",
            "brand_name": os.getenv("APP_NAME", "Enterprise CRM"),
            "service_name": os.getenv("SERVICE_NAME_CRM", "octo-enterprise-crm"),
            "app_name": "crm",
            "rum_configured": False,
            "max_ttl": MAX_TTL_SECONDS,
            "csp_nonce": nonce,
        },
    )

page_router = _PAGE_ROUTER
```

**Adapt:** `/admin/stress-test` route returning `stress_test_admin.html` with the same context dict; add `dns_domain`, `drilldown_links` keys for UI-SPEC §Observability drilldowns block.

**Host-bound enforcement** (coordinator.py lines 300-361 — must be copied or imported, per RESEARCH Anti-Patterns §4):
```python
_ADMIN_SURFACE = "admin.octodemo.cloud"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}

def _request_host(request: Request) -> str:
    raw_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.hostname
        or ""
    )
    raw_host = raw_host.split(",", 1)[0].strip().lower()
    if raw_host.startswith("[") and "]" in raw_host:
        return raw_host[1:raw_host.index("]")]
    return raw_host.rsplit(":", 1)[0] if ":" in raw_host else raw_host

def _configured_admin_hosts() -> set[str]:
    hosts = {_ADMIN_SURFACE}
    parsed = urlparse(cfg.crm_base_url or "")
    if parsed.hostname:
        hosts.add(parsed.hostname)
    dns_domain = (getattr(cfg, "dns_domain", "") or "").strip()
    if dns_domain:
        hosts.add(f"admin.{dns_domain}")
        hosts.add(f"crm.{dns_domain}")
    return hosts

def _require_admin_host(request: Request) -> str:
    host = _request_host(request)
    if host in _LOCAL_HOSTS or host in _configured_admin_hosts():
        return host
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="OCI Coordinator is only available from admin.octodemo.cloud.",
    )
```

**Decision:** Refactor `_require_admin_host` / `_request_host` into a shared helper (`crm/server/modules/_admin_host.py`) and import from both `coordinator.py` and the new `stress_test.py`. Do **not** re-implement.

**Three-channel audit emit** (combining chaos/admin.py lines 57-59 + coordinator.py lines 264-282 + RESEARCH Pattern 5):

The chaos analog uses a minimal logger:
```python
def _audit(event: str, **fields: Any) -> None:
    record = {"event": event, **fields, "ts": time.time()}
    logger.info("chaos_audit %s", json.dumps(record, default=str))
```

The coordinator analog uses the canonical push_log + OTel span (coordinator.py lines 264-282 + 458-476):
```python
tracer = tracer_fn()
with tracer.start_as_current_span("admin.coordinator.query") as span:
    span.set_attribute("admin.actor", actor.get("username", "unknown"))
    span.set_attribute("admin.page", page)
    span.set_attribute("coordinator.host", host)
    ...
    push_log(
        "INFO",
        "Admin coordinator query evaluated",
        **{
            "app.module": "admin",
            "admin.actor": actor.get("username", "unknown"),
            "coordinator.host": host,
            "coordinator.scope": _PROJECT_SCOPE,
            ...
        },
    )
```

**Adapt for D-15 MELTS shape:** wrap each endpoint in `with tracer.start_as_current_span("admin.stress.<event>")` then call `push_log("INFO", f"stress_test.{event}", run_id=..., admin_user=..., admin_role=..., rps_requested=..., duration_requested=..., scenario=..., target_service=..., target_host=..., source_pod=..., status=..., reason=...)`. Add an OCI Monitoring counter increment `octo_apm_demo/stress_run_count` via a new helper in `shop/server/observability/oci_monitoring.py` (or a local lightweight publisher in CRM — planner decides). The `push_log` helper already injects `trace_id`/`span_id`/`oracleApmTraceId` (see logging_sdk.py lines 548-554), so D-15's `trace_id` / `span_id` fields are auto-populated.

**Internal-key proxy pattern to call the stress runner** (simulation.py lines 655-713):
```python
headers = outbound_headers(build_correlation_id("drone-proxy"))
if cfg.drone_shop_internal_key:
    headers["X-Internal-Service-Key"] = cfg.drone_shop_internal_key
try:
    async with httpx.AsyncClient(timeout=10.0) as client:
        if method == "POST":
            resp = await client.post(target, content=body,
                                     headers={**headers, "Content-Type": "application/json"})
        ...
except (httpx.ConnectError, httpx.TimeoutException) as e:
    push_log("WARNING", f"Drone shop unreachable: {type(e).__name__}")
    return {"status": "unreachable", "reason": f"{type(e).__name__}: drone shop not responding"}
```

**Adapt:** New config field `cfg.octo_stress_runner_internal_key` (env `OCTO_STRESS_RUNNER_INTERNAL_KEY`) and `cfg.octo_stress_runner_base_url` (env `OCTO_STRESS_RUNNER_BASE_URL`, default `http://octo-stress-runner.octo-stress.svc.cluster.local:8080`). Wrap the POST in a try/except matching the `unreachable` shape — UI-SPEC §State copy already declares HTTP 503 = "Stress runner unavailable. Confirm octo-stress-runner Deployment is healthy in the OKE cluster."

---

### `crm/server/modules/admin.py` (EDIT, controller, request-response)

**Self-edit:** Add `stress-operator` to the existing role allow-list.

**Current state** (admin.py line 20):
```python
_ALLOWED_ROLES = {"admin", "manager", "viewer", "user", "chaos-operator"}
```

**Target state:**
```python
_ALLOWED_ROLES = {"admin", "manager", "viewer", "user", "chaos-operator", "stress-operator"}
```

This is the only edit needed in `admin.py`. Per D-12 this role is **optional**; the primary auth gate is `require_admin_user` (admin role).

---

### `crm/server/main.py` (EDIT, wiring, startup)

**Self-edit:** Mirror the chaos router include block (main.py lines 217-220):
```python
# Chaos control surface (CRM only — shop has no write endpoints).
from server.chaos.admin import router as chaos_admin_router, page_router as chaos_admin_page_router
app.include_router(chaos_admin_router)
app.include_router(chaos_admin_page_router)
```

**Target:**
```python
# Stress test surface (CRM only — admin-host-bound).
from server.modules.stress_test import router as stress_admin_router, page_router as stress_admin_page_router
app.include_router(stress_admin_router)
app.include_router(stress_admin_page_router)
```

---

### `crm/server/templates/base.html` (EDIT, nav entry)

**Self-edit:** Add one `<li>` under the "Admin" separator (base.html lines 67-86):
```html
<li><a href="/admin" data-journey="nav_admin" class="{% if nav_key == 'admin' %}active{% endif %}">Admin</a></li>
<li><a href="/settings" data-journey="nav_simulation" class="{% if nav_key == 'settings' %}active{% endif %}">Simulation</a></li>
```

**Insert after the Admin entry:**
```html
<li><a href="/admin/stress-test" data-journey="nav_stress" class="{% if nav_key == 'stress' %}active{% endif %}">Stress Test</a></li>
```

UI-SPEC §Page chrome locks `Stress Test` as the label. No new CSS selectors — reuses `.nav-menu li a.active` from `style.css`.

---

### `deploy/k8s/oke/shop/deployment.yaml` (EDIT, HPA)

**Self-edit.** Existing HPA block (lines 370-394):
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: octo-drone-shop
  namespace: ${K8S_NAMESPACE_SHOP}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: octo-drone-shop
  minReplicas: 2
  maxReplicas: 4
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 75
```

**Target per D-03:** `maxReplicas: 10`, CPU 60, memory 70, plus a third `type: External` metric block for `shop_request_rate` with target `averageValue: "30"` (RESEARCH Pattern 1). Add `behavior:` block with `scaleUp.stabilizationWindowSeconds: 30` and `scaleDown.stabilizationWindowSeconds: 300` per Pitfall 1.

The External metric block is the new pattern (from RESEARCH Pattern 1 lines 298-307) — no in-repo analog exists yet:
```yaml
- type: External
  external:
    metric:
      name: shop_request_rate
      selector:
        matchLabels:
          service: octo-drone-shop
    target:
      type: AverageValue
      averageValue: "30"
```

---

### `deploy/k8s/oke/apm-java-demo/deployment.yaml` (EDIT, add HPA block)

**Analog:** `deploy/k8s/oke/shop/deployment.yaml:370-394` (HPA block above).

**Action:** Append a new `---` document at end of the file with an HPA targeting `octo-apm-java-demo`, `min=2, max=6`, CPU 65, RPS-per-pod 20 (D-03). Same External-metric shape. Same `behavior:` block.

---

### `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml` (EDIT, helm)

**Self-edit.** Existing template (lines 1-29) wraps the HPA in `{{- if and .Values.shop.enabled .Values.shop.autoscaling.enabled }}`. Phase 7 keeps the gate and adds a nested `{{- if .Values.shop.autoscaling.rps.enabled }}` block for the External metric — guarantees D-05 backward compat ("default false").

**Target additions:**
```yaml
  maxReplicas: {{ .Values.shop.autoscaling.maxReplicas }}     # bumped to 10 in values.yaml
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.shop.autoscaling.cpuTargetUtilization }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ .Values.shop.autoscaling.memoryTargetUtilization }}
{{- if .Values.shop.autoscaling.rps.enabled }}
    - type: External
      external:
        metric:
          name: {{ .Values.shop.autoscaling.rps.metricName | default "shop_request_rate" }}
          selector:
            matchLabels:
              service: octo-drone-shop
        target:
          type: AverageValue
          averageValue: "{{ .Values.shop.autoscaling.rps.targetPerPod }}"
{{- end }}
  behavior:
    {{- toYaml .Values.shop.autoscaling.behavior | nindent 4 }}
{{- end }}
```

---

### `deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml` (NEW)

**Analog:** `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml` (exact clone). Same wrapping `{{- if .Values.javaGateway.autoscaling.enabled }}`. Same metric blocks. Adapt names (`octo-apm-java-demo`) and values keys (`javaGateway.autoscaling.*`).

---

### `deploy/helm/octo-apm-demo/values.yaml` (EDIT)

**Self-edit.** Existing shop autoscaling block (values.yaml lines 120-125):
```yaml
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 6
    cpuTargetUtilization: 70
    memoryTargetUtilization: 75
```

**Target:** Bump `maxReplicas: 10`, `cpuTargetUtilization: 60`, `memoryTargetUtilization: 70`. Add D-05-gated rps subsection:
```yaml
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    cpuTargetUtilization: 60
    memoryTargetUtilization: 70
    rps:
      enabled: false                  # D-05: gated
      metricName: shop_request_rate
      targetPerPod: 30
    behavior:
      scaleUp:
        stabilizationWindowSeconds: 30
        policies:
          - type: Percent
            value: 100
            periodSeconds: 30
          - type: Pods
            value: 2
            periodSeconds: 30
        selectPolicy: Max
      scaleDown:
        stabilizationWindowSeconds: 300
        policies:
          - type: Percent
            value: 25
            periodSeconds: 60
        selectPolicy: Min
```

Add a new top-level block:
```yaml
stressRunner:
  enabled: false                      # default off; flipped on at operator-window apply
  namespace: octo-stress
  image:
    repository: octo-stress-runner
    region: ""
    tenancy: ""
    tag: ""
  internalKeySecret: octo-stress-runner-key
```

And a `javaGateway.autoscaling` block mirroring the shop one (`maxReplicas: 6`, CPU 65, rps target 20).

---

### `deploy/k8s/oke/stress-runner/namespace.yaml` + `deployment.yaml` + `service.yaml`

**Analog:** `tools/traffic-generator/k8s/deployment.yaml` lines 8-80 (full file).

**Namespace pattern** (lines 8-15):
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: octo-traffic
  labels:
    app.kubernetes.io/part-of: octo-apm-demo
    app.kubernetes.io/component: traffic-generator
```

**Adapt:** namespace `octo-stress`, component `stress-runner`.

**Deployment pattern** (lines 18-80):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: octo-traffic-generator
  namespace: octo-traffic
  labels:
    app: octo-traffic-generator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: octo-traffic-generator
  template:
    metadata:
      labels:
        app: octo-traffic-generator
    spec:
      containers:
        - name: traffic
          image: ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-traffic-generator:${IMAGE_TAG:-latest}
          env:
            - name: OCTO_TRAFFIC_SHOP_BASE_URL
              value: "https://shop.${DNS_DOMAIN}"
            - name: OCTO_TRAFFIC_OTEL_EXPORTER_OTLP_ENDPOINT
              valueFrom:
                secretKeyRef:
                  name: octo-apm
                  key: endpoint
                  optional: true
            ...
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
```

**Adapt:** replicas=1, name `octo-stress-runner`, image `octo-stress-runner`, container port 8080, env adds `OCTO_STRESS_RUNNER_INTERNAL_KEY` (from a new k8s Secret), `OTEL_SERVICE_NAME=octo-stress-runner` (RESEARCH Anti-Pattern §3), and the same `octo-apm` OTLP secret references (the OTLP secret is already in the namespace pattern). Resources bumped to allow k6 to actually push load: requests `cpu: 250m, memory: 256Mi`; limits `cpu: 2, memory: 512Mi`. Imagepullsecret `ocir-pull-secret` per the apm-java-demo/deployment.yaml line 38-39 pattern.

**Service:** ClusterIP, port 8080 → targetPort 8080. No Ingress (per RESEARCH architecture diagram — "no Ingress").

**RBAC** (deploy/k8s/oke/stress-runner/rbac.yaml — **no analog in repo**): create a minimal `ServiceAccount: octo-stress-runner` with no Role bindings. The pod does not call the Kubernetes API; it only spawns a k6 subprocess. Document this explicitly in a header comment.

---

### `deploy/oke/configure-cluster-autoscaler.sh` (NEW, script)

**Analog:** `deploy/oke/install-oci-kubernetes-monitoring.sh` lines 1-120 — same "oci-cli + jq + idempotent install/update + dry-run" shape.

**Header + usage pattern** (lines 1-41):
```bash
#!/usr/bin/env bash
# Install Oracle's OCI Kubernetes Monitoring solution for the current cluster.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy/oke/install-oci-kubernetes-monitoring.sh
...
EOF
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    "") ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac
```

**Defaults pattern** (lines 43-62):
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

: "${OCI_PROFILE:=emdemo}"
: "${OCI_REGION:=us-phoenix-1}"
: "${OKE_CLUSTER_NAME:=octo-apm-demo-oke}"
...
: "${APPLY:=true}"
: "${SERVER_DRY_RUN:=true}"
```

**Tool-check pattern** (lines 63-77):
```bash
require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

require_tool oci
require_tool jq
require_tool kubectl
```

**Context-check guard** (lines 96-103):
```bash
if [[ "${SKIP_CONTEXT_CHECK}" != "true" ]]; then
    current_context="$(kubectl config current-context 2>/dev/null || true)"
    if [[ "${current_context}" != "${OKE_CLUSTER_NAME}" ]]; then
        echo "Current kubectl context is '${current_context:-unset}', expected '${OKE_CLUSTER_NAME}'." >&2
        echo "Set SKIP_CONTEXT_CHECK=true only after verifying the target cluster." >&2
        exit 1
    fi
fi
```

**Adapt for D-04:** keep `set -euo pipefail`, `usage()`, `require_tool oci/jq/kubectl`, defaults via `: "${VAR:=default}"`, and `SKIP_CONTEXT_CHECK` gate. Add the RESEARCH Pattern 2 idempotency body: `oci ce cluster list` → resolve `CLUSTER_ID`; `oci ce cluster list-addons` → detect existing `ClusterAutoscaler`; if `--apply` then `read -p "Type the cluster name to confirm apply: " CONFIRM` and call `install-addon` or `update-addon` with `--from-json file://$(dirname "$0")/cluster-autoscaler-config.json`. Default mode = dry-run (echo "would install/update"); only `--apply` mutates. Hard-fail if `COMPARTMENT_ID` is unset.

---

### `deploy/oke/cluster-autoscaler-config.json` (NEW)

**No in-repo analog.** Use the JSON shape from RESEARCH Pattern 2 lines 337-368 verbatim. Keep `nodes` value as `"2:4:${OKE_NODE_POOL_OCID}"` with envsubst at apply time so no live OCID is committed (KB-456 / global SEC rule: no live OCIDs).

---

### `tools/stress-runner/octo_stress_runner/main.py` (NEW, FastAPI wrapper)

**Analog:** `crm/server/chaos/admin.py` for the FastAPI router/Pydantic skeleton (lines 19-80 above) plus RESEARCH Pattern 3 lines 416-530 for the subprocess + concurrency=1 + SIGTERM specifics.

**Imports:** From chaos/admin.py — `from fastapi import APIRouter, Depends, HTTPException, Request, status` + `from pydantic import BaseModel, Field`. Add: `asyncio`, `os`, `signal`, `uuid`, `asynccontextmanager`, `dataclasses.dataclass/field`.

**Auth:** Single env var `OCTO_STRESS_RUNNER_INTERNAL_KEY` (required at startup — raise on import if missing). Header `X-Internal-Service-Key` checked on every internal endpoint. Mirrors `cfg.drone_shop_internal_key` pattern from simulation.py lines 674-675 (`headers["X-Internal-Service-Key"] = cfg.drone_shop_internal_key`).

**Endpoints (D-12 internal contract):** `POST /internal/run` (HTTP 202 on success, 409 if active), `POST /internal/clear`, `GET /internal/state`, `GET /internal/healthz`. All require the internal-key header. Use the RESEARCH Pattern 3 body verbatim (the lock/ActiveRun dataclass/asyncio subprocess shape).

**OTel:** `OTEL_SERVICE_NAME=octo-stress-runner` (separate service entity from CRM) — RESEARCH Anti-Patterns §3. The wrapper itself emits one span per `/internal/run` POST; k6 emits its own spans via native OTLP (`--out experimental-opentelemetry`).

---

### `tools/stress-runner/scenarios/*.js` (NEW, 3 files)

**Analogs:**
- `checkout_journey.js` ← `shop/k6/checkout-load.js` (lines 1-53 verbatim, with header substitution).
- `catalog_browse.js` ← `shop/k6/checkout-load.js` (drop the cart+checkout POSTs; keep just the `GET /api/products`).
- `login_burst.js` ← RESEARCH Pattern 4 lines 536-569 (no exact in-repo analog).

**Required headers** (RESEARCH Pattern 4 lines 554-562) on every request:
```js
headers: {
  'X-Octo-Stress-Target': 'oke',          // D-09 LB pin
  'X-Run-Id': RUN_ID,                     // propagates to APM
  'User-Agent': 'k6/octo-stress-runner',
  'Content-Type': 'application/json',
}
```

**Standard options block** (mirrors `shop/k6/checkout-load.js` lines 14-21):
```js
export const options = {
  vus: Number(__ENV.K6_VUS || 25),
  duration: __ENV.K6_DURATION || '60s',
  thresholds: { http_req_failed: ['rate<0.10'] },
  tags: { scenario: '<scenario_name>', run_id: RUN_ID },
};
```

---

### `shop/server/observability/oci_monitoring.py` (EDIT, add 5 D-17 metrics)

**Self-edit.** Existing `_build_metric_data` (lines 136-181) returns a list of `_point(name, value, unit)` calls. The helper `_point` (lines 146-158) builds the `PostMetricDataDetails`-shape dict with namespace `octo_apm_demo`, dimensions `serviceName/environment/runtime/instanceId`, and metadata `{unit}`.

**Adapt for D-17:** Add five new metric publish helpers (or extend `_build_metric_data`) — gauges `shop_pod_count`, `shop_request_rate`, `shop_cpu_saturation_pct`; counters `hpa_decision_event` (dim: `action: scale_up|scale_down`), `cluster_autoscaler_node_event` (dim: `action: add|remove`). Per D-17 dimensions: add `pod_name`, `namespace`, `run_id` per-point (not in the global `dimensions` dict, because `run_id` and `pod_name` vary per-event). RESEARCH Anti-Pattern §2: keep `run_id` only on the bounded `stress_run_count` counter — do NOT put it on the gauge metrics.

The existing publisher loop (lines 184-267) already does instance/resource principal auth + the ingestion-endpoint override (KB-456). Reuse the same `client.post_metric_data(PostMetricDataDetails(metric_data=...))` call — do not introduce a parallel publisher.

**New helper signature** (planner picks the exact shape):
```python
def increment_stress_run(run_id: str, status: str) -> None:
    """Increment octo_apm_demo/stress_run_count with run_id + status dims."""
    ...
```

---

### `tools/la-saved-searches/oke-autoscaling-*.json` (NEW, 4 files)

**Analog:** `tools/la-saved-searches/errors-by-route.json` (full file):
```json
{
  "name": "octo-errors-by-route",
  "description": "5xx + 4xx response breakdown by HTTP route across shop + CRM. Fuels the 'error rate' widget on the operations dashboard.",
  "displayName": "OCTO — errors by route (last 1h)",
  "queryString": "'Log Source' = 'octo-shop-app-json' and http_status >= 400 | stats count() by route, http_status | sort -count | head limit = 50",
  "widgetType": "BAR_CHART"
}
```

**Adapt for D-19:** Four files matching the four saved searches in CONTEXT.md D-19:
1. `oke-autoscaling-hpa-events.json` — `'Log Source' = 'Kubernetes Logs' and Subsystem = 'hpa-controller' | stats count() by hpa_event, deployment | sort -Time`
2. `oke-autoscaling-ca-events.json` — Cluster Autoscaler add-on logs filter.
3. `oke-autoscaling-kubelet-pressure.json` — `NodeNotReady`, `ImagePullBackOff`, `OOMKilled`.
4. `oke-autoscaling-stress-audit.json` — filter `run_id is not null` over stress audit log entries.

**Apply script:** Reuse `tools/la-saved-searches/apply.sh` lines 1-36 — it iterates `*.json` in the directory and upserts via `oci log-analytics saved-search create-or-update`. No edits to apply.sh needed; the new JSONs auto-pick up.

---

### `site/workshop/lab-11-oke-autoscaling.md` (NEW)

**Analogs:**
- Structure from `site/workshop/lab-09-chaos-drill.md` lines 1-80 (header + Objective + Time budget + Prerequisites + numbered Steps + `RUN_ID=$(uuidgen)` pattern + APM/Monitoring/Log Analytics drill triplet).
- Alarm CLI from `site/workshop/lab-05-metric-and-alarm.md` lines 50-80 (`oci monitoring alarm create ...` shape with `--namespace octo_apm_demo` and `--query-text`).

**Lab 09 narrative arc to copy** (the run_id propagation contract — exactly Phase 7's pivot pattern):
```markdown
### 1. Create the run_id
The CRM Chaos Admin emits a `run_id` for every chaos profile launch.

### 3. Watch the symptoms
#### APM
filter: attributes."chaos.run_id" = '<RUN_ID>'
#### Monitoring
The shop.checkout.latency_p95 metric should climb...
#### Log Analytics
'Log Source' = 'octo-shop-app-json' and run_id = '<RUN_ID>' | head limit = 50
```

**Adapt for D-22:** seven steps (baseline → trigger Medium preset → watch HPA → watch CA → drill APM → drill Log Analytics → cool-down). Each step has APM / Monitoring / Log Analytics drill-down sections. Cross-link Labs 01, 05, 09. Include D-20 external drilldown link blocks (`lm.octodemo.cloud`, `phoenix.octodemo.cloud`, `openlit.octodemo.cloud`, `grafana.octodemo.cloud`).

---

### `site/operations/stress-demo-lb-routing.md` (NEW, runbook)

**Analog:** `site/operations/chaos.md` (operator-facing runbook for chaos enable). Structure: Purpose → Prerequisites → Steps → Rollback. Document `oci lb routing-policy update` to add a header-eq rule for `X-Octo-Stress-Target: oke` per D-09. Include verification curl: `curl -H "X-Octo-Stress-Target: oke" https://shop.${DNS_DOMAIN}/api/products -v` and instruct operator to inspect the response `Server` or backend hint to confirm OKE backend-set received the request.

---

### `tests/test_stress_demo_surface.py` (NEW)

**Analog:** `tests/test_unified_deploy_surface.py` lines 1-80.

**Imports + ROOT pattern** (lines 1-25):
```python
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]

def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")
```

**Manifest-assertion test shape** (lines 27-50):
```python
def test_unified_deploy_wrapper_exists() -> None:
    deploy_wrapper = ROOT / "deploy/deploy.sh"
    assert deploy_wrapper.exists(), "root unified deploy wrapper is missing"
    wrapper_text = deploy_wrapper.read_text(encoding="utf-8")
    assert "deploy-shop.sh" in wrapper_text
    ...

def test_root_oke_manifests_use_shop_and_crm_hostnames() -> None:
    shop_manifest = read_text("deploy/k8s/oke/shop/deployment.yaml")
    ...
    assert 'https://admin.${DNS_DOMAIN}' in shop_manifest
```

**Adapt to VALIDATION.md table:** one test per boundary row. Examples:
- `test_shop_hpa_max_replicas_bumped_to_ten()` — read `deploy/k8s/oke/shop/deployment.yaml`, assert `maxReplicas: 10` present.
- `test_java_hpa_block_added()` — assert HPA block exists in apm-java-demo manifest.
- `test_helm_rps_metric_is_default_off()` — `helm template ... --set autoscaling.rps.enabled=false` produces no External metric block (D-05).
- `test_configure_cluster_autoscaler_idempotent()` — script contains both `install-addon` and `update-addon` branches; defaults to dry-run; reads `cluster-autoscaler-config.json`.
- `test_stress_test_module_uses_admin_auth()` — `read_text("crm/server/modules/stress_test.py")` contains `require_admin_user`, `_require_admin_host`, `push_log`, hard caps `ge=1, le=200`, `ge=10, le=600`.
- `test_stress_admin_role_in_allowed_roles()` — `crm/server/modules/admin.py` `_ALLOWED_ROLES` includes `stress-operator`.
- `test_stress_runner_manifest_exists()` — namespace, deployment, service yaml all parse and reference `octo-stress` namespace.
- `test_stress_runner_scenarios_have_otlp_and_run_id_headers()` — read each `tools/stress-runner/scenarios/*.js`, assert `X-Octo-Stress-Target` and `X-Run-Id` headers and `experimental-opentelemetry`.
- `test_oci_monitoring_publishes_new_d17_metrics()` — `shop/server/observability/oci_monitoring.py` contains `shop_pod_count`, `shop_request_rate`, `shop_cpu_saturation_pct`, `hpa_decision_event`, `cluster_autoscaler_node_event`, `stress_run_count`.
- `test_la_saved_searches_oke_autoscaling_present()` — four new `oke-autoscaling-*.json` files exist under `tools/la-saved-searches/`.
- `test_lab_11_cross_links_labs_01_05_09()` — assert lab-11 markdown contains links to lab-01, lab-05, lab-09.

---

### `tests/test_unified_deploy_surface.py` (EDIT)

**Self-edit.** Extend the existing surface test to catch the new stress-runner manifest and the CA configure script in `deploy/verify.sh`-style assertions. Pattern: read the relevant file → assert key strings. Mirror `test_unified_deploy_wrapper_exists` (lines 27-34) and `test_root_oke_manifests_use_shop_and_crm_hostnames` (lines 41-63).

Add:
- Assert `deploy/k8s/oke/stress-runner/deployment.yaml` exists.
- Assert `deploy/oke/configure-cluster-autoscaler.sh` exists and is executable (`os.access(p, os.X_OK)`).
- Assert `deploy/verify.sh` (line 1-482) calls the new manifest validation (planner decides exact insertion point in verify.sh).

---

## Shared Patterns

### Authentication: admin-only host-bound

**Source:** `crm/server/modules/_authz.py` lines 35-42 + `crm/server/modules/coordinator.py` lines 300-361 (host helpers).

**Apply to:** `crm/server/modules/stress_test.py` (every endpoint).

```python
# In router endpoint:
actor = require_admin_user(request)
host = _require_admin_host(request)
tracer = tracer_fn()
with tracer.start_as_current_span("admin.stress.apply") as span:
    span.set_attribute("admin.actor", actor.get("username", "unknown"))
    span.set_attribute("admin.host", host)
    span.set_attribute("admin.scope", "octo-apm-demo")
    ...
```

**Refactor recommendation:** extract `_request_host` + `_require_admin_host` + `_configured_admin_hosts` to a shared `crm/server/modules/_admin_host.py` (RESEARCH Anti-Pattern §4 says do not re-implement).

### Three-channel MELTS audit (Log + Metric + Trace, all with run_id)

**Sources:**
- Trace: `crm/server/modules/coordinator.py:264-282` (`tracer.start_as_current_span` + `span.set_attribute`).
- Log: `shop/server/observability/logging_sdk.py:525-555` (`push_log` auto-injects `trace_id`, `span_id`, `oracleApmTraceId`).
- Metric: `shop/server/observability/oci_monitoring.py:136-181` (`_build_metric_data` + `_point`).

**Apply to:** every stress run lifecycle event (`started`, `running`, `stopped`, `expired`, `error`). The single `run_id` (UUID generated in `stress_test.py`) is the cross-channel key per D-15 / D-22.

```python
# Pattern (from RESEARCH Pattern 5 + coordinator.py):
with tracer.start_as_current_span("admin.stress.apply") as span:
    span.set_attribute("stress.run_id", run_id)
    span.set_attribute("stress.scenario", scenario)
    span.set_attribute("stress.rps_requested", rps)
    ...
push_log(
    "INFO",
    "stress_test.apply",
    run_id=run_id,
    admin_user=actor.get("username"),
    admin_role=actor.get("role"),
    rps_requested=rps,
    duration_requested=duration,
    scenario=scenario,
    target_service="shop",
    target_host=target_host,
    source_pod=cfg.service_instance_id,
    status="started",
    reason="",
)
# OCI Monitoring counter (new helper):
oci_monitoring.increment_stress_run(run_id=run_id, status="started")
```

### CSP-nonced inline JS in admin templates

**Source:** `crm/server/templates/chaos_admin.html:49` (`<script nonce="{{ csp_nonce }}">`). The `csp_nonce` template variable is passed in from the page route (chaos/admin.py:249 `nonce = getattr(request.state, "csp_nonce", "")` then included in template context).

**Apply to:** `stress_test_admin.html` inline JS block. Do **not** introduce external script files.

### Internal-key cross-service authentication

**Source:** `crm/server/modules/simulation.py:673-675` (`X-Internal-Service-Key` header + `cfg.drone_shop_internal_key`).

**Apply to:** CRM → stress-runner calls. New config field `cfg.octo_stress_runner_internal_key` (env `OCTO_STRESS_RUNNER_INTERNAL_KEY`). Stress runner validates the same header on every `/internal/*` endpoint.

### Helm template gating with `{{- if }}`

**Source:** `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml:1` (`{{- if and .Values.shop.enabled .Values.shop.autoscaling.enabled }}`).

**Apply to:** `stress-runner-deployment.yaml` (gate on `.Values.stressRunner.enabled` — default `false` per D-05 spirit), `java-gateway-hpa.yaml` (gate on `.Values.javaGateway.autoscaling.enabled`), the RPS External-metric block inside `shop-hpa.yaml` (gate on `.Values.shop.autoscaling.rps.enabled` — default `false`, D-05 explicit).

### Test file shape (manifest-string assertions)

**Source:** `tests/test_unified_deploy_surface.py:1-80`. Each test reads a manifest with `read_text(relative_path)` then `assert` against literal substrings. No fixtures, no httpx; offline-feasible per VALIDATION.md.

**Apply to:** all 12+ tests in `tests/test_stress_demo_surface.py`.

### LA saved-search apply

**Source:** `tools/la-saved-searches/apply.sh:1-36` — iterates every `*.json` and calls `oci log-analytics saved-search create-or-update`. The script already auto-discovers new files; no edits required.

**Apply to:** the four new `oke-autoscaling-*.json` files. Add them to the same directory; `apply.sh` picks them up.

---

## No Analog Found

Files with no close match in the codebase. Planner should use RESEARCH.md patterns instead:

| File | Role | Data Flow | Reason | RESEARCH.md Reference |
|------|------|-----------|--------|-----------------------|
| `deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml` | helm values | declarative | No prometheus-adapter or external-metrics adapter exists in repo today | RESEARCH §Standard Stack + §Don't Hand-Roll + Pitfall 2 (three-step validation) |
| `deploy/k8s/oke/stress-runner/rbac.yaml` | RBAC | declarative | No bare `ServiceAccount`-only manifests in current repo; all existing deployments share the default SA | RESEARCH §Recommended Project Structure (stress-runner subdir) — minimal SA, no Role/RoleBinding needed |
| `deploy/oke/cluster-autoscaler-config.json` | JSON config | declarative | OKE CA add-on config is unique to this phase | RESEARCH Pattern 2 lines 337-368 (verbatim shape) |
| `tools/stress-runner/Dockerfile` (implied) | container image | build | No existing Python+`k6`-binary multi-stage Dockerfile in repo | RESEARCH §Build Strategy + control-plane VM build (CLAUDE.md global cloud-build rule) |
| `tools/stress-runner/pyproject.toml` (implied) | package config | build | Each existing FastAPI service has its own; planner picks the closest (`tools/traffic-generator/pyproject.toml` is the nearest analog) | follow `tools/traffic-generator/pyproject.toml` |

---

## Metadata

**Analog search scope:**
- `crm/server/templates/` — found chaos_admin.html exact analog
- `crm/server/modules/` + `crm/server/chaos/` — found chaos/admin.py (template) + coordinator.py (host-bound) + simulation.py (internal-key proxy)
- `deploy/k8s/oke/` — found shop/deployment.yaml HPA block + apm-java-demo/deployment.yaml structure
- `deploy/helm/octo-apm-demo/` — found shop-hpa.yaml + values.yaml shape
- `deploy/oke/` — found install-oci-kubernetes-monitoring.sh as CA-script analog
- `tools/traffic-generator/k8s/` — found deployment.yaml as stress-runner analog
- `tools/la-saved-searches/` — found errors-by-route.json + apply.sh as LA dashboard analog
- `shop/server/observability/` — found oci_monitoring.py + logging_sdk.py for metrics/audit
- `shop/k6/`, `crm/k6/` — found checkout-load.js + stress_test.js as k6 scenario analogs
- `site/workshop/`, `site/operations/` — found lab-09-chaos-drill.md + lab-05-metric-and-alarm.md + chaos.md
- `tests/` — found test_unified_deploy_surface.py as test-shape analog

**Files scanned:** 24 directly opened; ~60 grepped.

**Pattern extraction date:** 2026-05-18.
