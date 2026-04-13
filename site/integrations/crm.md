# CRM Integration

The Drone Shop connects to the Enterprise CRM Portal for customer enrichment, order synchronization, storefront metadata coordination, and CRM-driven catalog publishing. Every call creates a distributed trace visible in OCI APM.

## Integration Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/integrations/crm/sync-customers` | POST | Pull CRM customers → local DB |
| `/api/integrations/crm/sync-order` | POST | Push order → CRM as ticket |
| `/api/integrations/crm/customer-enrichment` | GET | Enrich local customer with CRM data |
| `/api/integrations/crm/ticket-products` | GET | CRM ticket → product recommendations |
| `/api/integrations/crm/health` | GET | Health check with distributed trace |
| `/api/integrations/crm/customers` | GET | List local customers (optional CRM refresh) |

## Current Ownership Model

- **CRM is the source of truth** for products, stock, price, category, storefront assignment, and storefront metadata.
- **Shop is the source of truth** for cart, checkout, and storefront session behavior.
- **Shared Oracle ATP** allows both services to correlate the same order, customer, and product lifecycle from different operational surfaces.
- **Public CRM URLs stay public**: browser responses and docs point to `https://crm.octodemo.cloud`, while backend service-to-service calls may still target the in-cluster CRM service URL.

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
ENTERPRISE_CRM_URL="http://enterprise-crm-portal.enterprise-crm.svc.cluster.local"
CRM_PUBLIC_URL="https://crm.octodemo.cloud"

# If the backend can call the public CRM directly instead of the in-cluster
# service, ENTERPRISE_CRM_URL may also be public:
ENTERPRISE_CRM_URL="https://crm.octodemo.cloud"
```

### Why both URLs exist

| Variable | Audience | Purpose |
|---|---|---|
| `ENTERPRISE_CRM_URL` | Backend service-to-service | Private or public URL used by the shop server when calling CRM APIs |
| `CRM_PUBLIC_URL` | Browser/public docs | Public CRM URL used for links, redirects, and user-visible integration surfaces |

This prevents internal `.svc.cluster.local` hostnames from leaking into storefront responses while still allowing efficient in-cluster traffic.
