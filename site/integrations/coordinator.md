# OCI Coordinator Integration

The OCI Coordinator's Remediation Agent v2 consumes telemetry from both services and executes automated remediations via MCP tools.

## Architecture

```mermaid
flowchart TD
    subgraph Apps ["Monitored Applications"]
        Shop["Drone Shop<br/>98 routes"]
        CRM["CRM Portal<br/>73 routes"]
    end

    subgraph OCI ["OCI Telemetry Sources"]
        APM["OCI APM<br/>Traces + Topology"]
        Logging["OCI Logging<br/>+ Log Analytics"]
        Monitoring["OCI Monitoring<br/>Alarms"]
        CloudGuard["Cloud Guard<br/>Problems"]
        VSS["VSS<br/>Vulnerabilities"]
        Audit["OCI Audit<br/>API Events"]
        DBMgmt["DB Management<br/>Performance Hub"]
        OPSI["Ops Insights<br/>SQL Warehouse"]
    end

    subgraph Coordinator ["OCI Coordinator"]
        Detect["Detect Agent"]
        Correlate["Correlate Agent"]
        Diagnose["Diagnose Agent<br/>(LLM)"]
        Runbook["Runbook Agent"]
        Approve["Approval Gate"]
        Execute["Execute Agent"]
        Verify["Verify Agent"]
    end

    Shop -.-> APM
    Shop -.-> Logging
    Shop -.-> Monitoring
    CRM -.-> APM
    CRM -.-> Logging

    APM --> Detect
    Logging --> Detect
    CloudGuard --> Detect
    VSS --> Detect
    Audit --> Detect

    Detect --> Correlate --> Diagnose --> Runbook --> Approve --> Execute --> Verify

    Execute -->|kubectl| Shop
    Execute -->|HTTP| CRM
    Execute -->|MCP| CloudGuard
```

## Telemetry Signals Consumed

| Signal | Source | Coordinator Use |
|---|---|---|
| **Cloud Guard Problems** | `cloudguard_list_problems` | Primary security alert feed |
| **Security Score** | `cloudguard_get_security_score` | Posture assessment |
| **VSS Vulnerabilities** | `vss_list_host_scans` | Container/host vuln detection |
| **Audit Events** | `audit_list_events` | Suspicious API activity |
| **APM Traces** | OCI APM API | Error rate, latency correlation |
| **App Logs** | Log Analytics (`oracleApmTraceId`) | Root cause analysis |
| **Custom Metrics** | OCI Monitoring | Alarm triggers |
| **DB Performance** | DB Management / OPSI | SQL root cause |

## Remediation Actions

### Infrastructure (via kubectl MCP)

| Action | Command | When |
|---|---|---|
| Stop service | `kubectl scale --replicas=0` | Service compromised |
| Restart service | `kubectl rollout restart` | Memory leak, stale state |
| Scale up | `kubectl scale --replicas=N` | High load detected |
| Scale down | `kubectl scale --replicas=1` | Load subsided |

### Application (via HTTP)

| Action | Endpoint | When |
|---|---|---|
| Inject CPU stress | `POST /api/simulate/configure {"cpu_spike": true}` | Stress testing |
| Inject DB latency | `POST /api/simulate/db-latency {"delay_seconds": N}` | Resilience testing |
| Generate load | `POST /api/simulate/generate-orders {"count": N}` | Load testing |
| Stop chaos | `POST /api/simulate/reset` | After investigation |
| Force order sync | `POST /api/orders/sync` | Sync backlog resolution |
| Error burst | `POST /api/simulate/error-burst {"count": N}` | Alert testing |

### Security (via MCP tools)

| Action | MCP Tool | When |
|---|---|---|
| Resolve problem | `cloudguard_remediate_problem(id, RESOLVE)` | After fix confirmed |
| Dismiss false positive | `cloudguard_remediate_problem(id, DISMISS)` | False positive confirmed |
| Kill bastion session | `bastion_terminate_session(id)` | Unauthorized access |

## Coordinator Workflow

```
1. DETECT  → Scan Cloud Guard, VSS, Audit, APM for anomalies
2. CORRELATE → Match findings to APM traces and Log Analytics entries
3. DIAGNOSE → LLM analyzes root cause from correlated telemetry
4. RUNBOOK → Generate structured remediation steps
5. APPROVE → Human-in-the-loop gate (or auto-approve in sandbox)
6. EXECUTE → Run fix via kubectl, HTTP, or MCP tool
7. VERIFY → Re-scan to confirm remediation success
```

## Console Drilldown URLs

Both services expose drilldown URLs for the coordinator to link findings to OCI Console:

| Service | Endpoint | Returns |
|---|---|---|
| Shop | `/api/observability/360` → `pillars` | APM, Logging, OPSI, DB Management URLs |
| CRM | `/api/integrations/topology` → `drilldown_products` | APM, Log Analytics, OPSI, DB Management URLs |

## Demo Scenario: CPU Spike → Detection → Remediation

```bash
# 1. Coordinator triggers stress test via CRM proxy
POST /api/simulate/configure {"cpu_spike": true}

# 2. OCI Monitoring alarm fires (app.errors.rate > threshold)
# 3. Cloud Guard detects unusual activity
# 4. Coordinator DETECT agent picks up the signals
# 5. CORRELATE links alarm → APM traces → Log Analytics
# 6. DIAGNOSE identifies cpu_spike simulation flag
# 7. RUNBOOK generates: "Reset simulation state"
# 8. APPROVE (human confirms)
# 9. EXECUTE: POST /api/simulate/reset
# 10. VERIFY: re-check /health → healthy
```
