# CRM Integration

The Drone Shop connects to the Enterprise CRM Portal for customer enrichment, order synchronization, storefront metadata coordination, and CRM-driven catalog publishing. Every call creates a distributed trace visible in OCI APM.

## Integration Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/integrations/schema` | GET | Machine-readable cross-service contract (OpenAPI 3.1 subset) |
| `/api/integrations/crm/sync-customers` | POST | Pull CRM customers → local DB |
| `/api/integrations/crm/sync-order` | POST | Push order → CRM as ticket |
| `/api/integrations/crm/customer-enrichment` | GET | Enrich local customer with CRM data |
| `/api/integrations/crm/ticket-products` | GET | CRM ticket → product recommendations |
| `/api/integrations/crm/health` | GET | Health check with distributed trace |
| `/api/integrations/crm/customers` | GET | List local customers (optional CRM refresh) |

## Cross-service authentication

All cross-service calls carry the shared `X-Internal-Service-Key` header
whenever `INTERNAL_SERVICE_KEY` is configured:

```http
POST /api/orders HTTP/1.1
Host: crm.<tenancy>
Content-Type: application/json
X-Internal-Service-Key: <shared-secret>
```

- Both services read `INTERNAL_SERVICE_KEY` from their own secret store
  (in OKE: `octo-auth/internal-service-key`).
- If either side has the key unset, that side silently allows unauthenticated
  traffic — the `integration_schema` endpoint will not advertise the scheme.
- Rotate by updating the shared secret on both deployments within the
  same rollout window; old/new keys are not supported simultaneously.

## Idempotency

Order sync payloads include a stable `idempotency_token` computed as
`uuid5(namespace, "<order_id>:<source>")`. CRM SHOULD use the composite
`(source_system, source_order_id, idempotency_token)` to deduplicate
retries — re-posting the same order MUST NOT create a second invoice.

## Current Ownership Model

- **CRM is the source of truth** for products, stock, price, category, storefront assignment, and storefront metadata.
- **Shop is the source of truth** for cart, checkout, and storefront session behavior.
- **Shared Oracle ATP** allows both services to correlate the same order, customer, and product lifecycle from different operational surfaces.
- **Public CRM URLs stay public**: browser responses and docs point to `https://crm.example.cloud`, while backend service-to-service calls may still target the in-cluster CRM service URL.

## Distributed Tracing

W3C `traceparent` headers are auto-injected by `HTTPXClientInstrumentor`:

```
Shop (span: integration.crm.sync_customers)
  └── HTTP GET crm:8080/api/customers (traceparent auto-injected)
       └── CRM (span: customers.list)
            └── SQL: SELECT * FROM customers
```

Visible in OCI APM → Topology as edges between services.

## Data Flow

### Customer Sync
```
CRM /api/customers → normalize → upsert local customers table
```
- Cached for 5 minutes (unless `force=true`)
- Rate limited to 500 customers per sync
- Normalizes field names across CRM variants

### Order Sync
```
Checkout → create local order → POST CRM /api/orders
```
- Upserts CRM customer if not found
- Embeds OCTO order ID in CRM notes
- Circuit breaker protects against CRM outages

### Catalog Sync
```
CRM product/storefront edit → CRM DB write → POST /api/integrations/crm/catalog-sync
```
- Operators create new drones, batteries, accessories, and other inventory in CRM
- Stock and sellable state changes are made in CRM, not in the public storefront
- Shop consumes the synced catalog as a customer-facing read model
- CRM publishes catalog batches to the shop through the authenticated `/api/integrations/crm/catalog-sync` endpoint
- Public storefront pages no longer expose private CRM cluster names

## Configuration

```bash
# Canonical name used by new tenancies. Falls back to ENTERPRISE_CRM_URL
# when SERVICE_CRM_URL is unset (legacy alias).
SERVICE_CRM_URL="<internal-crm-base-url>"
CRM_PUBLIC_URL="https://crm.<your-tenancy-domain>"
INTERNAL_SERVICE_KEY="<shared-secret-between-shop-and-crm>"
```

### Env var naming across the two services

| Variable | Audience | Purpose |
|---|---|---|
| `SERVICE_CRM_URL` (preferred) / `ENTERPRISE_CRM_URL` (legacy alias) | Backend service-to-service | URL used by the shop server when calling CRM APIs |
| `CRM_PUBLIC_URL` | Browser/public docs | Public CRM URL used for links, redirects, and user-visible integration surfaces |
| `INTERNAL_SERVICE_KEY` | Both sides | Shared secret attached as `X-Internal-Service-Key` header |

This prevents internal service hostnames from leaking into storefront responses while still allowing efficient private network traffic.
