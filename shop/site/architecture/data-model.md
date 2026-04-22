# Data Model

The Drone Shop and Enterprise CRM Portal share the same Oracle ATP instance. Tables are organized by domain.

## Table Organization

### Core
`users`, `products`, `customers`, `orders`, `order_items`, `shops`

### Commerce
`cart_items`, `reviews`, `coupons`, `shipments`, `warehouses`

### Marketing
`campaigns`, `leads`

### Operations
`page_views`, `audit_logs`, `security_events`, `services`, `tickets`, `ticket_messages`

### AI Assistant
`assistant_sessions`, `assistant_messages`

### Workflow Gateway
`workflow_runs`, `query_executions`, `component_snapshots`

## Entity-Relationship Diagram

```mermaid
erDiagram
    customers ||--o{ orders : "places"
    orders ||--|{ order_items : "contains"
    products ||--o{ order_items : "included in"
    customers ||--o{ reviews : "writes"
    products ||--o{ reviews : "receives"
    products ||--o{ cart_items : "added to"
    orders ||--o{ shipments : "tracked by"
    campaigns ||--o{ leads : "generates"
    users ||--o{ audit_logs : "performs"
    customers ||--o{ tickets : "opens"
    products ||--o{ tickets : "related to"
    services ||--o{ tickets : "related to"
    tickets ||--|{ ticket_messages : "contains"

    customers {
        int id PK
        string name
        string email
        string company
        string industry
        float revenue
    }

    orders {
        int id PK
        int customer_id FK
        float total
        string status
        string payment_method
    }

    products {
        int id PK
        string name
        string sku
        float price
        int stock
        string category
    }

    security_events {
        int id PK
        string attack_type
        string severity
        string endpoint
        string source_ip
        string trace_id
    }
```

## Database Observability

| Feature | How |
|---|---|
| Session tagging | `MODULE=octo-drone-shop`, `ACTION=<span_name>`, `CLIENT_IDENTIFIER=<trace_id>` |
| SQL ID enrichment | Oracle SQL_ID computed and attached to APM spans |
| DB Management | Performance Hub shows SQL execution from the app |
| Operations Insights | SQL Warehouse aggregates query patterns |
| Query instrumentation | SQLAlchemy events capture statement, execution time, row count |
