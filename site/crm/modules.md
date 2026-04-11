# CRM Modules

12 FastAPI router modules with 73 endpoints covering full CRM functionality.

## Module Map

| Module | Prefix | Routes | Key Functionality |
|---|---|---|---|
| `auth` | `/api/auth` | 7 | Login, register, session, logout, SSO (IDCS OIDC + PKCE) |
| `customers` | `/api/customers` | 4 | CRUD with search, sort, filter (SQLi-vulnerable) |
| `orders` | `/api/orders` | 6 | CRUD, backlog tracking, external sync trigger |
| `products` | `/api/products` | 3 | Product catalog management |
| `invoices` | `/api/invoices` | 4 | Invoicing, PDF generation, payment processing |
| `tickets` | `/api/tickets` | 4 | Support ticket management |
| `reports` | `/api/reports` | 3 | Custom report builder (SQL injection risk) |
| `files` | `/api/files` | 5 | File upload/download (path traversal, XXE, SSRF) |
| `admin` | `/api/admin` | 6 | User management, config, debug, audit logs |
| `campaigns` | `/api/campaigns` | 6 | Campaign + lead management |
| `shipping` | `/api/shipping` | 6 | Shipment tracking, warehouse management |
| `analytics` | `/api/analytics` | 6 | Overview, geo, funnel, revenue, performance |
| `simulation` | `/api/simulate` | 20+ | Chaos controls, data generation, proxy |
| `integrations` | `/api/integrations` | 6 | Topology, drone-shop health, security summary |
| `observability` | `/api/observability` | 6 | 360 dashboard, console config, RUM ingestion |

## Middleware Stack

```
CORSMiddleware (outermost)
  → GeoLatencyMiddleware (region-based latency)
    → ChaosMiddleware (CPU, memory, errors, slow queries)
      → SessionGateMiddleware (auth enforcement)
        → MetricsMiddleware (HTTP RED)
          → TracingMiddleware (8+ spans per request)
```

## Authentication

| Method | Flow | Stored In |
|---|---|---|
| Password | POST /api/auth/login → session_id cookie | `user_sessions` table (ATP) |
| SSO | OIDC + PKCE → IDCS → callback → session_id | `user_sessions` table (ATP) |
| Service Key | `X-Internal-Service-Key` header | Config (env var) |

ATP-backed sessions enable session sharing across OKE replicas without sticky sessions.
