# OCI API Gateway module — `octo-edge-gateway`

Fronts shop + CRM with route-aware policies and centralises the edge
log feed into Log Analytics.

## Routes

| Path | Auth | Rate limit (rpm) | Backend |
|---|---|---|---|
| `/api/public/*` | none | 100 (per IP) | Shop |
| `/api/partner/*` | X-API-Key → CUSTOM_AUTHENTICATION Function | 1000 (per key) | Shop |
| `/api/crm/*` | inherits from caller | unset | CRM |
| `/api/admin/*` | IDCS JWT_AUTHENTICATION | 100 (per subject) | CRM |

CORS is pre-configured for `Content-Type`, `Authorization`,
`X-API-Key`, `X-Run-Id`; response exposes `X-Trace-Id` +
`X-Workflow-Id` per the correlation contract.

## Apply

```hcl
module "edge_gateway" {
  source = "./modules/api_gateway"

  compartment_id     = var.compartment_id
  display_name       = "octo-edge-gateway"
  gateway_subnet_id  = var.edge_subnet_id
  shop_backend_url   = "https://drone.${var.dns_domain}"
  crm_backend_url    = "https://backend.${var.dns_domain}"
  log_group_id       = var.edge_log_group_id
  idcs_jwks_uri      = var.idcs_jwks_uri
  idcs_issuer        = var.idcs_issuer
}
```

Then pipe its logs into Log Analytics by adding to root `main.tf`:

```hcl
module "la_pipeline_edge" {
  source              = "./modules/log_pipeline"
  compartment_id      = var.compartment_id
  display_name        = "la-pipeline-octo-edge"
  source_log_group_id = var.edge_log_group_id
  source_log_id       = module.edge_gateway.execution_log_id
  la_namespace        = var.la_namespace
  la_log_group_id     = var.la_log_group_id
  la_source_name      = "octo-edge-gateway-json"
}
```

## Register the `octo-edge-gateway-json` LA source

Define the source + parser in the same pattern as `tools/create_la_source.py`
but with a parser that extracts API-Gateway access-log fields:

```
timestamp | client_ip | request_method | request_path
response_status | latency_ms | apiVersion | subject (JWT)
```

See workshop Lab 06 for the WAF equivalent — the principle is the
same.

## Partner API-key authorizer

The partner route uses `CUSTOM_AUTHENTICATION` which requires an OCI
Function. The scaffold:

```python
# functions/partner_authorizer/func.py
import json
import os

def handler(ctx, data=None):
    body = json.loads(data.getvalue()) if data else {}
    api_key = body.get("headers", {}).get("x-api-key", "")

    # Look up in Vault — cache-ready via OCI secret versioning.
    known_keys = _load_allowed_keys_from_vault()
    if api_key in known_keys:
        return {
            "active": True,
            "context": {"partner_id": known_keys[api_key]["partner_id"]},
            "expiresAt": known_keys[api_key].get("expiresAt"),
        }
    return {"active": False, "message": "Invalid API key"}

def _load_allowed_keys_from_vault():
    # Implementation deferred — see KG-028.
    return {}
```

Until the Function + Vault integration lands, partner routes will
reject every request (fail-closed) — this is safer than a permissive
default.

## Tracked follow-ups

- **KG-028**: Build the partner-authorizer Function + Vault store for
  API keys.
- **KG-029**: Add OCI Events trigger that pages on-call when
  `httpStatus >= 500` count exceeds threshold on any route in the
  last 5 min.
- **KG-030**: Wire the edge-fuzz executor in
  `octo-load-control/executor.py` to drive the
  `edge-auth-failure-burst` profile.
