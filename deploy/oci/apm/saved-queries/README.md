# APM saved queries

These descriptors are the project-owned Trace Explorer saved-query catalog for
the OCTO APM demo. Oracle stores Trace Explorer saved queries as
`management-saved-search` resources; these files keep the exact query text,
scope, parameters, and Log Analytics pivots reviewable in source control.

## Local validation

Run the source asset gate before importing saved queries into OCI:

```bash
python3 -m pytest -q tests/test_observability_asset_contract.py tests/test_log_analytics_attack_assets.py
```

The required APM descriptors are:

- `assistant-genai-llmetry.json`
- `checkout-end-to-end.json`
- `db-slow-spans.json`
- `login-auth-flow.json`
- `payment-java-sidecar.json`
- `platform-workflows.json`
- `service-errors.json`
- `trace-drilldown.json`

This local gate only validates repository assets. Live OCI import remains a
separate operator step; this phase does not run Terraform apply or create OCI
resources.

## Apply

The helper is dry-run by default. It does not create Service Connector Hub
resources and does not run Terraform.

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
./deploy/oci/apm/apply_saved_queries.sh --dry-run

OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
./deploy/oci/apm/apply_saved_queries.sh --apply
```

`APM_SAVED_QUERY_PROVIDER_ID` defaults to `apm-traces` and
`APM_SAVED_QUERY_PROVIDER_NAME` defaults to `Application Performance
Monitoring`. The `emdemo` tenancy currently exposes Trace Explorer saved
queries through provider id/name `APM`, so apply there with:

```bash
OCI_CLI_PROFILE=emdemo \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
APM_SAVED_QUERY_PROVIDER_ID=APM \
APM_SAVED_QUERY_PROVIDER_NAME=APM \
./deploy/oci/apm/apply_saved_queries.sh --apply
```

## Round trip

Every descriptor has at least one `logAnalyticsPivots` entry. The normal
operator path is:

1. Open the APM saved query and copy `TraceId`.
2. Open the named Log Analytics saved search.
3. Pass the trace id as `:trace_id`, or paste it into the Trace ID filter.
4. Use `Span ID`, `Request ID`, `Payment Gateway Request ID`, `Order ID`,
   `Assistant Session ID`, `LLM Prompt Hash`, or `Attack ID` for the next
   drilldown.

The canonical join key remains `TraceId` in APM and `Trace ID` in Log
Analytics, both populated from the W3C `trace_id`/`oracleApmTraceId` contract.
