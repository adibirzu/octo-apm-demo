---
name: private-demo-observability-triage
description: Use this skill whenever working on the private demo OCTO APM demo deployment, especially APM traces, RUM, Java app-server spans, SQL visibility, OCI Logging to Log Analytics, Cloud Guard OSQuery, Stack Monitoring, availability monitors, or demo-storyboard/attack-lab troubleshooting.
---

# Private Demo Observability Triage

Use this workflow to move quickly through private demo failures without damaging the
manual Load Balancer, SSL, host-routing, external DNS changes, or private
Langfuse/GenAI runtime settings.

## Fixed Private Demo Context

- OCI profile: `<OCI_PROFILE>`
- Compartment: `<COMPARTMENT_OCID>`
- APM domain: `<APM_DOMAIN_OCID>`
- APM endpoint: `<APM_DATA_UPLOAD_ENDPOINT>`
- Public hostnames: `shop.example.test`, `admin.example.test`
- Optional Langfuse hostname: `langfuse.example.test`
- Manual LB IP: `203.0.113.10`
- SSH config: `credentials/<profile>/ssh_config`
- Shop host alias: `<DEPLOYMENT_PREFIX>-shop`
- CRM host alias: `<DEPLOYMENT_PREFIX>-crm`

Do not run Terraform apply against the Load Balancer unless the listener,
certificate, hostnames, and routing-policy drift has first been codified or
ignored. Smoke test with `curl -k --resolve` while DNS is owned in the reference
tenancy.

## Private Live Documentation Evidence

When the operator asks for private guide screenshots, use live browser evidence
from the deployed shop and admin domains. Keep these artifacts private and
redact OCIDs, tenancy names, private IPs, wallet paths, credentials, and OCI
Console account headers before committing.

Screenshot and PDF regeneration commands must stay out of facilitator-facing
PDFs. Maintainer-only workflows may use the local capture tooling, but every
result must be reviewed before it is referenced by docs.

For OCI Console evidence, use the logged-in Chromium CDP session and pass
deployment-specific redaction terms through the environment:

```bash
OCI_CONSOLE_REDACT_TERMS="<tenancy-name>,<compartment-name>" \
OCI_CONSOLE_TARGET_URL="https://cloud.oracle.com/apm/apm-traces?region=<region>" \
node tools/demo-guide/capture_oci_console_screenshot.mjs oci-apm-trace-explorer-live
```

Current useful Console routes:

- Trace Explorer: `/apm/apm-traces`
- Real User Monitoring: `/apm/apm-traces/realusermonitoring`
- Availability Monitoring: `/apm/apm-traces/availabilitymonitoring`
- Log Explorer: `/loganalytics/explorer`
- Connector Hub: `/connector-hub`
- Stack Monitoring: `/apm/apm-stackmon`
- Logging logs: `/logging/logs`
- Cloud Guard Problems: `/cloud-guard/problems`
- Monitoring alarms: `/monitoring/alarms`

Artifacts:

- `site/assets/demo/private-live/*.png`
- `site/assets/demo/private-oci-console/*.png`
- `site/assets/demo/octo-private-demo-facilitator-guide.pdf`
- `output/pdf/octo-private-demo-facilitator-guide.pdf`
- `site/observability-v2/private-demo-facilitator-guide.md`
- `site/observability-v2/private-livelabs-threat-hunting.md`
- `site/observability-v2/private-oci-threat-hunting-workflow.md`

If the live admin page is older than the branch and does not show the
**Synthetic Users** card, do not fabricate a screenshot. Document the redeploy
prerequisite and capture the card after the branch build is deployed.

## First Checks

Run these before changing resources:

```bash
oci --profile <OCI_PROFILE> iam compartment get \
  --compartment-id <COMPARTMENT_OCID>

curl -k -fsS --resolve shop.example.test:443:203.0.113.10 \
  https://shop.example.test/ready

curl -k -fsS --resolve admin.example.test:443:203.0.113.10 \
  https://admin.example.test/ready
```

For host work, prefer SSH through the jump host:

```bash
ssh -F credentials/<profile>/ssh_config <DEPLOYMENT_PREFIX>-shop 'hostname; date; systemctl --no-pager status octo-compute.service octo-java-apm.service'
ssh -F credentials/<profile>/ssh_config <DEPLOYMENT_PREFIX>-crm 'hostname; date; systemctl --no-pager status octo-compute.service'
```

OCI Run Command currently runs as `ocarun`; privileged commands may fail when
`sudo` prompts for a password.

## APM Trace Triage

1. Trigger one clean request from the admin page or API.
2. Capture the returned `trace_id`.
3. Look for these services only in private demo views:
   - `octo-drone-shop`
   - `enterprise-crm-portal`
   - `octo-java-app-server`
   - the configured ATP service name
4. For SQL visibility, confirm spans include `DbStatement`, `DbOracleSqlId`,
   `db.statement.preview`, `db.connection_name`, and `peer.service`.
5. For Java app-server visibility, call:

```bash
curl -k -fsS --resolve shop.example.test:443:203.0.113.10 \
  https://shop.example.test/api/shop/app-server/health
```

If the APM App Servers details page is empty, check the Java APM metric
dimensions before rebuilding the whole app. This private demo failure has already
appeared as `Appserver=false` on `oracle_apm_monitoring` JVM metrics:

```bash
oci monitoring metric list --profile <OCI_PROFILE> \
  --compartment-id <COMPARTMENT_OCID> \
  --namespace oracle_apm_monitoring \
  --name HeapUsed \
  --dimension-filters '{"ResourceId":"<APM_DOMAIN_OCID>"}'
```

The Java sidecar entrypoint must include these OCI APM Java agent flags:

```text
-Dcom.oracle.apm.agent.resource.appserver=true
-Dcom.oracle.apm.agent.resource.appserver.name=${APM_SERVICE_NAME}
-Dcom.oracle.apm.agent.metric.collect.wait.for.appserver=false
```

After the Java sidecar is rebuilt/restarted, rerun the metric query and
confirm the dimensions move from `Appserver=false` to app-server visibility
for `ServiceName=octo-java-app-server`.

## App Logs In Span Context

If the APM span details page shows `Logs: 0`, first confirm whether the app
logs are reaching OCI Logging/Log Analytics. The Python apps also add compact
`app.log` span events to both the active custom span and the bound request
server span; those are what should populate the span-level log/event view.
The durable log drilldown path remains OCI Logging -> Service Connector -> Log
Analytics.

For FastAPI traces, be careful which span is selected in APM. The visible
`<service>: POST /path` span is the auto-instrumented server span, while
custom `middleware.entry`, `response.finalize`, checkout, payment, and
simulation spans are children. If only child spans have `app.log` events,
the server span can show `Logs: 0`. The request middleware must bind
`trace.get_current_span()` at dispatch entry with
`bind_request_span(...)` and reset it in `finally` so every `push_log()` call
adds the same compact event to the server span as well as the current child
span.

The known SDK failure signature is:

```text
OCI Logging put_logs failed: Unrecognized keyword arguments: defaultloglevel
```

That means the app image still has the old `LogEntryBatch(defaultloglevel=...)`
payload. Rebuild/redeploy Shop and CRM from a revision where
`shop/server/observability/logging_sdk.py` and
`crm/server/observability/logging_sdk.py` create `LogEntryBatch(source, type,
subject, entries)` only, set `LogEntry.time` to a timezone-aware datetime, and
include `timestamp`, `level`, `message`, `oracleApmTraceId`, and
`oracleApmSpanId` inside `LogEntry.data`.

After rebuilding and restarting the app containers, generate one fresh trace
and verify both log paths:

```bash
TRACE_ID=<trace-id-from-response-header>
oci logging-search search-logs --profile <OCI_PROFILE> \
  --time-start <start-rfc3339> \
  --time-end <end-rfc3339> \
  --search-query "search \"<COMPARTMENT_OCID>\" | where data.oracleApmTraceId = '${TRACE_ID}' | sort by datetime desc" \
  --limit 10

oci apm-traces trace trace get --profile <OCI_PROFILE> \
  --apm-domain-id <APM_DOMAIN_OCID> \
  --trace-key "${TRACE_ID}" \
  --time-trace-started-gte <start-rfc3339> \
  --time-trace-started-lt <end-rfc3339>
```

The first command should return durable OCI Logging rows. The second command
should show `logs` entries named `app.log` on the root FastAPI SERVER span;
if only child spans have `app.log`, check that middleware still calls
`bind_request_span(trace.get_current_span())` before custom spans start.

## Assistant LLMetry And Langfuse

The assistant endpoint is:

```bash
curl -k -fsS --resolve shop.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -X POST https://shop.example.test/api/shop/assistant/query \
  -d '{"message":"Compare Skydio X10 payload and endurance","session_id":"triage-session"}'
```

Expected span/log fields:

- `shop.assistant.query` and, when OCI GenAI is configured,
  `shop.assistant.genai`
- `assistant.session_id`, `assistant.provider`, `assistant.model_id`
- `assistant.guardrail.allowed`, `assistant.guardrail.reason`,
  `assistant.documents_grounded`
- `llm.prompt.hash`, `llm.response.hash`, `llm.prompt.length`,
  `llm.response.length`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` when the
  provider returns usage
- `langfuse.trace.name`, `langfuse.session.id`,
  `langfuse.observation.type` when Langfuse OTLP export is enabled

Raw prompts and responses are disabled by default. Keep
`LLMETRY_CAPTURE_CONTENT=false` unless the operator explicitly asks for a
controlled, redacted-content demo. Langfuse project keys go in
`LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` or their `*_FILE` variants;
do not put the Langfuse platform secrets from `/opt/octo/langfuse.env` into
tracked app runtime templates.

If Langfuse is empty but OCI APM has assistant spans:

1. Check `/ready` for `langfuse_configured: true`.
2. Confirm app runtime has `LANGFUSE_ENABLED=true`, `LANGFUSE_HOST`,
   `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` or
   `LANGFUSE_SECRET_KEY_FILE`.
3. Check the app startup logs for `OTel OTLP exporter -> Langfuse`.
4. Query OCI APM for the same `trace_id`; if APM has `llm.prompt.hash`, the
   app instrumentation is healthy and the remaining issue is Langfuse routing,
   credentials, or project configuration.

Before publishing, scan tracked and newly added files only. Ignored
`credentials/<profile>/`, Terraform state, per-tenancy tfvars, live
screenshots, and generated private PDFs must stay out of Git:

```bash
(git ls-files; git ls-files --others --exclude-standard) \
  | grep -vE '^(credentials|output|tmp)/' \
  | xargs -r rg -n '<private-domain>|<profile-name>|<actual-ocid>|<actual-datakey>|<actual-private-ip>'
```

## Demo Storyboard

Use the admin page **Demo Storyboard** button, or call:

```bash
curl -k -fsS --resolve admin.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -X POST https://admin.example.test/api/simulate/drone-shop/demo-storyboard \
  -d '{"persona":"Field operations buyer","quantity":2,"source_ip":"198.51.100.42","card":{"brand":"visa","number":"4242424242424242"}}'
```

Expected telemetry:

- browser/RUM page activity on the shop
- Python shop checkout spans
- Java app-server quote and payment spans
- order and support ticket logs with `oracleApmTraceId`
- payment simulation attributes without raw card numbers

## Synthetic Users And APM Users

Use the admin page **Synthetic Users** button or call the shop endpoint
through the preserved Load Balancer route:

```bash
curl -k -fsS --resolve shop.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -H "X-Internal-Service-Key: ${INTERNAL_SERVICE_KEY}" \
  -X POST https://shop.example.test/api/synthetic/users/run \
  -d '{"domain":"apex.example.test","count":12,"order_count":6,"delete_after_days":7}'
```

The VM cron-equivalent scheduler is `octo-synthetic-users.timer`; inspect it
with:

```bash
ssh -F credentials/<profile>/ssh_config <DEPLOYMENT_PREFIX>-shop \
  'systemctl --no-pager status octo-synthetic-users.timer octo-synthetic-users.service; cat /tmp/octo-synthetic-users.last.json 2>/dev/null || true'
```

The browser runner and app templates set `window.apmrum.username` from
`octoSyntheticUserEmail` before `apmrum.min.js` loads. If APM Users is empty,
run one browser journey with `OCTO_BROWSER_SYNTHETIC_USER_DOMAIN` set, then
check RUM sessions for `UserName` and custom dimensions
`synthetic_user_enabled` and `synthetic_user_domain`. Keep tracked defaults on
`apex.example.test`; private domains belong only in ignored credential/env
files.

## Attack Lab

Use the admin page **Generate Attack** button, or call:

```bash
curl -k -fsS --resolve admin.example.test:443:203.0.113.10 \
  -H 'Content-Type: application/json' \
  -X POST https://admin.example.test/api/simulate/drone-shop/attack-lab \
  -d '{"source_ip":"203.0.113.77","external_status_code":503,"user_agent":"curl/8.4.0 octo-attack-lab"}'
```

Expected telemetry:

- `security.attack.kill_chain` root span
- MITRE stage spans for `T1190`, `T1059`, `T1046`, `T1218`, `T1543`, `T1005`
- Java sidecar attack span
- external error span
- SQL error span against the Autonomous Database
- logs with `security.attack.id`, `mitre.technique_id`, `client.address`,
  `server.address`, `destination.ip`, `destination.port`, `osquery.query`,
  and `oracleApmTraceId`

## OSQuery and Log Analytics

Current known blocker: Service Connector Hub quota in the private demo
compartment has returned `service-connector-count available=0`. Existing
shared connectors do not route the `<DEPLOYMENT_PREFIX>` OCI Logging log group.
Do not delete or modify shared connectors without explicit operator
approval.

The consolidated connector helper should include these log display names by
default:

```text
octo-app
<DEPLOYMENT_PREFIX>-app-stdout
<DEPLOYMENT_PREFIX>-os
octo-security
octo-chaos-audit
<DEPLOYMENT_PREFIX>-waf
<DEPLOYMENT_PREFIX>-cloudguard-raw
<DEPLOYMENT_PREFIX>-cloudguard-query-results
```

Prepare Cloud Guard Instance Security saved queries:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
./deploy/oci/ensure_cloud_guard_advanced.sh
```

Run the attack-lab OSQueries after deployment:

```bash
DRY_RUN=false RUN_ADHOC=true \
OSQUERY_INSTANCE_IDS=<shop-instance-ocid>,<crm-instance-ocid> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
./deploy/oci/ensure_cloud_guard_advanced.sh
```

Export Cloud Guard OSQuery results into OCI Logging for Log Analytics:

```bash
DRY_RUN=false ATTACK_ID=<attack-id> ADHOC_QUERY_ID=<adhoc-query-ocid> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_ID=<custom-log-ocid> \
./deploy/oci/export_osquery_results_to_logging.sh
```

Create the consolidated Log Analytics route only when quota is available:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_GROUP_ID=<OCI_LOG_GROUP_OCID> \
LA_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
./deploy/oci/ensure_log_analytics_connectors.sh
```

Import or verify these Log Analytics assets:

- `deploy/oci/log_analytics/searches/attack-lab-detections.sql`
- `deploy/oci/log_analytics/searches/attack-lab-trace-timeline.sql`
- `deploy/oci/log_analytics/searches/osquery-attack-findings.sql`
- `deploy/oci/log_analytics/dashboards/attack-lab-command-center.json`

## Availability Monitoring

Dry-run first:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
OVERRIDE_DNS_IP=203.0.113.10 \
./deploy/oci/ensure_availability_monitors.sh
```

Apply only after the dry run shows the expected monitor names and targets.

## Verification Loop

Before deployment:

```bash
python -m compileall -q shop/server crm/server
PYTHONPATH=shop python -m pytest shop/tests -q
PYTHONPATH=crm python -m pytest crm/tests -q
python -m pytest tests -q
bash -n deploy/compute/install.sh deploy/oci/ensure_cloud_guard_advanced.sh deploy/oci/export_osquery_results_to_logging.sh
docker compose -f deploy/compute/app-compose.yml config
```

On the shop VM, run Java tests after syncing the repo:

```bash
cd /opt/octo/repo/services/apm-java-demo && mvn -q test
```

## Resource Manager 404 Triage

If the OCI Console test/deploy flow returns
`NotAuthorizedOrNotFound(404)` from `https://cloud.oracle.com/stacks/create`,
check the URL first. The supported deploy-button path is
`https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=...`; the
shorter `/stacks/create` route is stale and can fail before Resource Manager
imports the zip.

If the URL is correct, verify these in order:

```bash
curl -I -L "https://github.com/example-org/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip"

oci resource-manager stack list --profile <OCI_PROFILE> \
  --compartment-id <COMPARTMENT_OCID>
```

The user still needs Resource Manager create/import rights in the selected
tenancy and compartment. Read access alone proves the profile can see stacks,
but it does not prove permission to create a stack, create a private template,
upload zip configuration source content, or run Resource Manager jobs.
