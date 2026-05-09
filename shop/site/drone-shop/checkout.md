# Checkout Flow

End-to-end order lifecycle from cart to shipment, with full observability at every step.

## Flow

```mermaid
sequenceDiagram
    participant Browser
    participant Shop as Drone Shop
    participant PGW as Payment Gateway Emulator
    participant Java as Java Processor Simulator
    participant CRM as Enterprise CRM
    participant ATP as Oracle ATP
    participant APM as OCI APM

    Browser->>Shop: POST /api/cart/add (product_id, quantity)
    Shop->>ATP: SELECT product (validate stock)
    Shop->>ATP: INSERT/UPDATE cart_items
    Shop-->>Browser: {status: "added"}
    Browser->>APM: RUM: shop.add_to_cart

    Browser->>Shop: POST /api/shop/checkout (checkout_idempotency_key, payment_details)
    Shop->>APM: span: shop.checkout
    Shop->>ATP: SELECT cart_items + products
    Shop->>ATP: UPSERT customer
    Shop->>ATP: INSERT order + order_items
    Shop->>ATP: UPDATE products SET stock -= quantity
    Shop->>ATP: INSERT shipment
    Shop->>ATP: INSERT audit_log
    Shop->>PGW: payment.simulated.authorize (PCI-safe context)
    PGW->>APM: span: payment_gateway.emulator.authorize
    alt credit_card
        PGW->>APM: gateway_payment_received
        PGW->>APM: card_data_received
        PGW->>APM: gateway_card_tokenization
        PGW->>APM: internal_antifraud_screening
        PGW->>APM: card_network_routing
    else apple_pay / google_pay
        PGW->>APM: gateway_payment_received
        PGW->>APM: wallet_token_received
        PGW->>APM: gateway_token_decryption
        PGW->>APM: network_token_cryptogram_validation
        PGW->>APM: internal_antifraud_screening
    end
    PGW->>Java: verification_antifraud_request
    Java-->>PGW: verification_antifraud_response
    PGW->>Java: processor_authorization_request
    Java-->>PGW: processor_authorization_response
    PGW->>APM: network_authorization_routing
    PGW->>APM: merchant_authorization_result
    Shop->>ATP: INSERT payment_transactions
    Shop->>ATP: INSERT payment_gateway_events
    Shop->>ATP: DELETE cart_items (session cleanup)
    Shop->>CRM: POST /api/orders (sync via traceparent)
    Shop-->>Browser: {order_id, tracking_number, total}
    Browser->>APM: RUM: shop.checkout_complete
```

## Pricing Logic

```
subtotal = SUM(price × quantity)
discount = apply_coupon(code, subtotal)
shipping = $0 if subtotal >= $5,000 else $149
total    = max(subtotal - discount, 0) + shipping
```

## Observability at Each Step

| Step | Span | Metrics | Log |
|---|---|---|---|
| Add to cart | `orders.cart.add` | `shop.business.cart.additions` | "Cart updated" |
| Checkout | `shop.checkout` | `shop.business.orders.created` | "Store checkout persisted" |
| Payment gateway | `payment_gateway.emulator.authorize` | `shop.business.payment.authorizations` | "Payment gateway ... request" |
| Wallet/card token | `payment_gateway.<method>.*` | - | `gateway_payment_received`, `card_data_received`, `gateway_card_tokenization`, `wallet_token_received`, `gateway_token_decryption`, `network_token_cryptogram_validation` |
| Antifraud verification | `payment_gateway.<method>.verification_*` | - | Java verification request/response with `payment.verification.decision` |
| Processor hop | `java_app_server.post.api.java-apm.payment.authorize` | `java_app_server` | "Java app-server sidecar call completed" |
| Gateway result | `payment_gateway.<method>.merchant_authorization_result` | - | `payment.gateway.request_id`, status, risk score, and decision source |
| Stock update | (SQLAlchemy auto) | - | - |
| Shipment | (SQLAlchemy auto) | `shop.business.shipments.created` | - |
| CRM sync | `integration.crm.sync_order` | `shop.business.crm.sync` | "Order synced to CRM" |

Payment gateway events are persisted in `payment_gateway_events` with
`trace_id`, `span_id`, `gateway_request_id`, method, network, step name, and
safe metadata. Raw PAN, CVV, and wallet tokens are not logged or persisted.

## Security Checks

| Check | Trigger | Security Span | Log Analytics pivots |
|---|---|---|---|
| Invalid `product_id` | Non-integer | `ATTACK:MASS_ASSIGN` | `Security Check=mass_assign`, `Security Endpoint=/api/cart/add`, `Cart Session ID`, `Trace ID` |
| Quantity > 20 | Rate limit | `ATTACK:RATE_LIMIT` | `Security Check=rate_limit`, `Cart Product ID`, `Cart Quantity`, `Client IP` |
| Missing/inactive product | IDOR attempt | `ATTACK:IDOR` | `Security Check=idor`, `Cart Product ID`, `OWASP Category=A01:2021`, `MITRE Technique ID=T1078` |
| Invalid quantity | Non-integer | `ATTACK:MASS_ASSIGN` | `Security Check=mass_assign`, `Security Product ID`, `Security Session ID`, `Trace ID` |

Each guardrail emits an APM `ATTACK:*` child span, a structured app log with
`oracleApmTraceId`, and a row in `security_events`. The Log Analytics saved
search `checkout-security-checks.sql` groups these real events by check,
endpoint, source IP, product, session, OWASP category, and MITRE technique.

Payment dashboards use real gateway logs and persisted gateway events:

- `payment-gateway-timeline.sql` reconstructs the ordered gateway step
  sequence for a `Payment Gateway Request ID`, trace id, or order id.
- `payment-risk-decisions.sql` groups authorization outcomes by payment
  method, network, wallet/card metadata, verification decision, processor
  decision, and risk score.
- `user-order-action-correlation.sql` joins password-login, checkout, order,
  payment, and guardrail records by authenticated user id, order id, and trace.
- `payment-security-command-center.json` combines payment timeline, payment
  risk, checkout security checks, user/order correlation, and trace drilldown
  widgets.
