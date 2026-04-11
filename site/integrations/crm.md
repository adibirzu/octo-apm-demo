# CRM Integration

The Drone Shop connects to the Enterprise CRM Portal for bidirectional customer and order synchronization, with every call creating a distributed trace visible in OCI APM.

## Integration Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/integrations/crm/sync-customers` | POST | Pull CRM customers → local DB |
| `/api/integrations/crm/sync-order` | POST | Push order → CRM as ticket |
| `/api/integrations/crm/customer-enrichment` | GET | Enrich local customer with CRM data |
| `/api/integrations/crm/ticket-products` | GET | CRM ticket → product recommendations |
| `/api/integrations/crm/health` | GET | Health check with distributed trace |
| `/api/integrations/crm/customers` | GET | List local customers (optional CRM refresh) |

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

## Configuration

```bash
ENTERPRISE_CRM_URL="http://enterprise-crm-portal.enterprise-crm.svc.cluster.local"
# or
ENTERPRISE_CRM_URL="https://crm.yourcompany.cloud"
```
