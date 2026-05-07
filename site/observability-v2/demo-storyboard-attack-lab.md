# Demo Storyboard and Attack Lab

The private demo admin page now has two guided lab controls:

- **Demo Storyboard** runs a realistic buyer journey: open the shop,
  select drones, place an order, authorize a dummy credit-card payment
  through the simulated gateway, and create a support ticket.
- **Attack Lab** runs a controlled security scenario that generates APM
  spans, OCI API Gateway route-policy evidence, Java app-server evidence,
  SQL error evidence, structured logs, MITRE attributes, and OSQuery findings.

## Demo storyboard path

Admin page:

```text
https://admin.example.test/settings
```

API trigger:

```bash
set -a; . credentials/<profile>/app-secrets.env; set +a

curl -k -fsS --resolve admin.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -H "X-Internal-Service-Key: ${INTERNAL_SERVICE_KEY}" \
  -X POST https://admin.example.test/api/simulate/drone-shop/demo-storyboard \
  -d '{
    "persona": "Field operations buyer",
    "quantity": 2,
    "source_ip": "198.51.100.42",
    "card": {"brand": "visa", "number": "4242424242424242"}
  }'
```

Expected evidence:

| layer | signal |
| --- | --- |
| Browser | RUM page/action events from the shop and admin pages |
| Shop app | `demo.storyboard.*`, `shop.checkout`, payment, and support-ticket spans |
| Java app-server | quote and payment authorization calls through `octo-java-app-server` |
| ATP | order, order item, shipment, payment status, and support ticket records |
| Logs | `oracleApmTraceId`, order id, ticket id, payment status, risk score |

The dummy card number is never logged. The app stores only card brand,
last four digits, and a generated demo token in the storyboard response.

## Synthetic users for APM Users

The VM scheduler runs `octo-synthetic-users.timer` every 10 minutes when
`SYNTHETIC_USERS_ENABLED=true`. It calls the shop internal endpoint,
creates or refreshes fictional Apex AD-style users, deletes older
synthetic user rows, and places a small batch of drone orders:

```bash
set -a; . credentials/<profile>/app-secrets.env; set +a

curl -k -fsS --resolve shop.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -H "X-Internal-Service-Key: ${INTERNAL_SERVICE_KEY}" \
  -X POST https://shop.example.test/api/synthetic/users/run \
  -d '{
    "domain": "apex.example.test",
    "count": 12,
    "order_count": 6,
    "delete_after_days": 7
  }'
```

The browser runner uses the same identity pool. Each Chromium session
sets `apmrum.username` before the OCI RUM browser agent loads, so the APM
Users page shows separate users instead of one anonymous synthetic
client. Override the domain only from ignored private deployment files.

## Attack lab path

API trigger:

```bash
set -a; . credentials/<profile>/app-secrets.env; set +a

curl -k -fsS --resolve admin.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -H "X-Internal-Service-Key: ${INTERNAL_SERVICE_KEY}" \
  -X POST https://admin.example.test/api/simulate/drone-shop/attack-lab \
  -d '{
    "source_ip": "203.0.113.77",
    "external_status_code": 503,
    "user_agent": "curl/8.4.0 octo-attack-lab"
  }'
```

The response returns `attack_id` and `trace_id`. Use both:

- `trace_id` opens OCI APM Trace Explorer.
- `attack_id` drives Log Analytics saved searches and dashboard filters.
- `api_gateway.request_id` pivots to route-policy, auth, quota, and backend
  decisions for the same attack.

## MITRE and server-hop mapping

| stage | tactic | technique | hop evidence |
| --- | --- | --- | --- |
| API Gateway edge control | Initial Access | `T1190` Exploit Public-Facing Application | `203.0.113.77` to public OCI API Gateway route `/api/shop/attack/simulate`, preserving trace context before the shop backend |
| initial access | Initial Access | `T1190` Exploit Public-Facing Application | `203.0.113.77` to `shop.example.test:443` through LB `203.0.113.10` |
| execution | Execution | `T1059` Command and Scripting Interpreter | app host `${SHOP_PRIVATE_IP}:${SHOP_APP_PORT}`, LOTL binary `bash` |
| discovery | Discovery | `T1046` Network Service Discovery | shop to Java app-server sidecar path on `${JAVA_APM_PRIVATE_IP}:${JAVA_APM_PORT}` |
| defense evasion | Defense Evasion | `T1218` System Binary Proxy Execution | LOTL binary `openssl` |
| persistence | Persistence | `T1543` Create or Modify System Process | systemd unit inventory |
| collection | Collection | `T1005` Data from Local System | wallet and DB access path inventory |

Each stage emits span attributes and structured log fields:

- `security.attack.id`
- `security.attack.stage`
- `mitre.technique_id`
- `mitre.tactic`
- `attack.entry_point`
- `attack.lotl_binary`
- `client.address`, `source.ip`
- `server.address`, `destination.ip`, `destination.port`
- `oci.api_gateway.request_id`, `oci.api_gateway.route`
- `oci.api_gateway.action`, `oci.api_gateway.policy.decision`
- `network.protocol.name`
- `oracleApmTraceId`

## OSQuery detections

Create or validate the Cloud Guard saved queries:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
./deploy/oci/ensure_cloud_guard_advanced.sh
```

Run ad-hoc queries against the shop and CRM instances:

```bash
DRY_RUN=false RUN_ADHOC=true \
OSQUERY_INSTANCE_IDS=<shop-instance-ocid>,<crm-instance-ocid> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
./deploy/oci/ensure_cloud_guard_advanced.sh
```

Export completed Cloud Guard OSQuery results into OCI Logging:

```bash
DRY_RUN=false ATTACK_ID=<attack-id> ADHOC_QUERY_ID=<adhoc-query-ocid> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_ID=<custom-log-ocid> \
./deploy/oci/export_osquery_results_to_logging.sh
```

The initial private demo run exported 246 normalized OSQuery result entries to
the `<DEPLOYMENT_PREFIX>-os` OCI custom log with
`ATTACK_ID=attack-851e80f8751b`. Service Connector Hub quota is currently
exhausted (`service-connector-count available=0`), so these rows are in
OCI Logging but are not yet visible in Log Analytics.

## Dashboards and searches

Import these assets after the Log Analytics connector/source mapping is
active. Use the quota-aware helper to create one consolidated route when
quota is available:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_GROUP_ID=<OCI_LOG_GROUP_OCID> \
LA_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
./deploy/oci/ensure_log_analytics_connectors.sh
```

| asset | purpose |
| --- | --- |
| `attack-lab-command-center.json` | attack command center dashboard |
| `api-gateway-edge-detections.sql` | API Gateway route policy, auth, quota, and backend decisions |
| `attack-lab-detections.sql` | grouped MITRE detections |
| `attack-lab-trace-timeline.sql` | ordered trace/log timeline |
| `osquery-attack-findings.sql` | OSQuery findings by host and instance |

The fastest operator flow is:

1. Click **Generate Attack** in the admin page.
2. Open the returned `trace_id` in APM Trace Explorer.
3. Filter `api-gateway-edge-detections.sql` by the returned `attack_id`.
4. Filter `attack-lab-trace-timeline.sql` by the returned `attack_id`.
5. Export OSQuery results with the same `ATTACK_ID`.
6. Refresh the Attack Lab Command Center dashboard.

For the private live delivery path, use the real screenshots and OCI Console
walkthrough in:

- [Private Live Demo Facilitator Guide](private-demo-facilitator-guide.md)
- [Private OCI Threat Hunting Workflow](private-oci-threat-hunting-workflow.md)

## Availability monitoring

Two APM Availability Monitoring REST monitors are enabled:

- `<DEPLOYMENT_PREFIX>-drones-ready-global` for
  `https://shop.example.test/ready`
- `<DEPLOYMENT_PREFIX>-admin-ready-global` for
  `https://admin.example.test/ready`

Both use the preserved LB IP `203.0.113.10` and run from Phoenix,
Ashburn, Frankfurt, London, Tokyo, and Sydney.
