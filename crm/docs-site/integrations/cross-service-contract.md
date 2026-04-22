# Cross-service integration contract

Enterprise CRM Portal and OCTO Drone Shop share a defined wire protocol
so either side can evolve without breaking the other. This page is the
authoritative reference — the same OpenAPI subset is served at
`/api/integrations/schema` on both services.

## Authentication

All cross-service calls carry the shared `X-Internal-Service-Key` header:

```http
POST /api/orders HTTP/1.1
Host: crm.<tenancy>
Content-Type: application/json
X-Internal-Service-Key: <shared-secret>
```

- Canonical env var: `INTERNAL_SERVICE_KEY` (both sides).
- Legacy alias still accepted: `DRONE_SHOP_INTERNAL_KEY` (emits a
  deprecation warning at startup).
- When the key is set, `POST /api/orders` rejects unauthenticated
  callers with `401`. When the key is empty the endpoint accepts
  anonymous traffic — this is the back-compat default.

## Idempotency contract

The calling service (Drone Shop) supplies the three dedup fields on
every order sync:

```json
{
  "customer_id": 42,
  "items": [{"product_id": 7, "quantity": 1, "unit_price": 49.99}],
  "source_system": "octo-drone-shop",
  "source_order_id": "100",
  "idempotency_token": "5e1a6db6-8c0e-5f1c-9c9a-3b0c2a1f0f01"
}
```

- `source_system` — logical name of the upstream service.
- `source_order_id` — stable id from the upstream system (retries use
  the same value).
- `idempotency_token` — stable UUID computed on the shop side from
  `uuid5(namespace, "<order_id>:<source>")`. Shop side freezes the
  namespace UUID forever to guarantee retries regenerate the same
  token.

CRM honors these fields verbatim instead of generating a new
`source_order_id`. A unique composite DB index on
`(source_system, source_order_id)` (or `idempotency_token`) is the
recommended way to enforce dedup at the persistence layer.

## Env var harmonization

| Concern | Canonical | Legacy aliases |
|---|---|---|
| Shop URL (CRM → Shop) | `SERVICE_SHOP_URL` | `OCTO_DRONE_SHOP_URL`, `MUSHOP_CLOUDNATIVE_URL` |
| CRM URL (Shop → CRM) | `SERVICE_CRM_URL` | `ENTERPRISE_CRM_URL` |
| Shared key | `INTERNAL_SERVICE_KEY` | `DRONE_SHOP_INTERNAL_KEY` (CRM side only) |

Either side emits a startup deprecation warning when only a legacy
name is set.

## Discovery

```bash
curl -s https://crm.<tenancy>/api/integrations/schema | jq
curl -s https://shop.<tenancy>/api/integrations/schema | jq
```

Both endpoints advertise the `InternalServiceKey` security scheme and
the order payload shape. Multi-tenancy tooling validates the contract
with a simple `jq` check before traffic flows.
