# Event generation guide

This page is the presenter-first map for generating OCTO APM Demo telemetry and
showing where each captured signal appears in OCI. Use placeholders in public
material; keep live URLs, OCIDs, credentials, and account-header screenshots out
of committed docs.

## Presenter workflow

For every scenario, use the same four-step loop:

1. **Generate** the event from the Shop or Admin page.
2. **Copy evidence keys** from the app output: `trace_id`, `order_id`,
   `payment_gateway_request_id`, `attack_id`, `ticket_id`, or assistant
   `session_id`.
3. **Open OCI APM** and explain the request path, latency, errors, SQL spans,
   Java sidecar spans, RUM session, or App Servers metrics.
4. **Open OCI Logging / Log Analytics** and prove the matching log rows with the
   same trace or business key.

The canonical join is always **APM `TraceId` ↔ Log Analytics `Trace ID`**, both
derived from `trace_id` / `oracleApmTraceId`.

## Scenario matrix

| Scenario | Where to click | Backend route | Primary APM view | Log Analytics search | Keys to copy |
| --- | --- | --- | --- | --- | --- |
| Customer login | Shop → Login | `POST /api/auth/login` | `OCTO APM - login/auth flow` | `auth-login-correlation` | `trace_id`, `request_id`, user id |
| Manual checkout | Shop → Cart & Checkout → **Place Order** | `POST /api/shop/checkout` | `OCTO APM - checkout end-to-end` | `checkout-payment-correlation` | `trace_id`, `order_id`, `payment_gateway_request_id` |
| Java health | Admin → Simulation → **Java Health** | `GET /api/simulate/drone-shop/java-health` → Shop Java sidecar | `OCTO APM - payment Java sidecar` | `service-error-triage` | `trace_id` when returned, Java path/status |
| Payment decline/timeout | Admin → Simulation → **Payment Decline Path** or **Payment Timeout Path** | `POST /api/simulate/drone-shop/payment-*` | `OCTO APM - payment Java sidecar` | `checkout-payment-correlation`, `payment-gateway-security-triage` | `payment_gateway_request_id`, response code, error type |
| Demo Storyboard | Admin → Simulation → **Run Story** | `POST /api/simulate/drone-shop/demo-storyboard` | `OCTO APM - checkout end-to-end` | `checkout-payment-correlation` | `trace_id`, `storyboard_id`, `order_id`, `ticket_id` |
| Synthetic Users | Admin → Simulation → **Generate Users** | `POST /api/simulate/drone-shop/synthetic-users` | APM RUM → Users / Sessions | `service-trace-log-coverage` | synthetic domain, generated count, order count |
| Attack Lab | Admin → Simulation → **Generate Attack** | `POST /api/simulate/drone-shop/attack-lab` | `OCTO APM - service errors` or trace id drilldown | `attack-lab-trace-timeline`, `api-gateway-edge-detections`, `attack-lab-detections` | `attack_id`, `trace_id`, API Gateway request id |
| Assistant LLMetry | Shop/Admin assistant action | `POST /api/admin/assistant/query` | `OCTO APM - assistant GenAI LLMetry` | `genai-assistant-llmetry` | `trace_id`, assistant session id, prompt hash |

## What each generated event should capture

### Manual checkout

Expected captured data:

- Browser RUM actions: `shop.add_to_cart`, `shop.checkout_start`,
  `shop.checkout_complete` or `shop.checkout_error`.
- Shop spans: `shop.checkout`, cart resolve, customer upsert, order persist,
  payment authorize, payment state persist, CRM order sync.
- Java sidecar spans when enabled: quote, authorize, verify, payment rail steps.
- Java payment calls carry `X-Request-Id`, `X-Workflow-Id=checkout`, and
  `X-Workflow-Step` so Java spans/logs join the same checkout timeline.
- SQL spans with `db.system=oracle`, `DbStatement`, and `DbOracleSqlId`.
- Structured logs with `oracleApmTraceId`, `orders.order_id`,
  `payment.gateway.request_id`, `payment.method`, `payment.status`, and safe
  card/wallet metadata.
- Gateway step payloads with safe `component_label` values for Google Pay,
  Apple Pay, Visa, Mastercard, the Java processor, and antifraud verification.
- ATP rows in `orders`, `payment_transactions`, `payment_gateway_events`, and
  `audit_logs` with authenticated user/order joins where present.

APM presentation path:

```text
Application Performance Monitoring -> Trace Explorer -> saved query
OCTO APM - checkout end-to-end
```

Log Analytics pivot:

```text
Run checkout-payment-correlation and add a literal filter:
'Trace ID' = '<TRACE_ID>'
-- or
'Payment Gateway Request ID' = '<PAYMENT_GATEWAY_REQUEST_ID>'
-- or
'Order ID' = '<ORDER_ID>'
```

### Demo Storyboard

The Demo Storyboard is the fastest one-click executive path. It creates a
linked Shop → Payment → Support → Java APM → ATP SQL path.

Expected captured data:

- root span `demo.storyboard.shop_journey`
- child spans `demo.storyboard.open_shop` and `demo.storyboard.add_drones`
- order id and support ticket id
- Java quote / authorization evidence
- structured app log `Demo storyboard completed`

Use this when you need a reliable trace before opening the OCI Console.

### Attack Lab

The Attack Lab generates a synthetic but correlated security story. It is safe
demo evidence, not a real exploit.

Expected captured data:

- APM spans with `security.attack.id`, `security.attack.stage`, MITRE fields,
  API Gateway route-policy evidence, Java external errors, Java SQL errors, and
  payment interception/redirect markers.
- App logs with `attack_id`, `trace_id`, `mitre.technique_id`,
  `oci.api_gateway.request_id`, source/destination fields, and safe payment
  threat metadata.
- Optional Cloud Guard / OSQuery rows exported later with the same `attack_id`.

APM presentation path:

```text
Application Performance Monitoring -> Trace Explorer -> filter by returned trace id
```

Log Analytics pivots:

```text
attack-lab-trace-timeline: 'Attack ID' = '<ATTACK_ID>'
api-gateway-edge-detections: 'Attack ID' = '<ATTACK_ID>'
attack-lab-detections: 'Attack ID' = '<ATTACK_ID>'
osquery-attack-findings: 'Attack ID' = '<ATTACK_ID>'
```

### Synthetic Users and RUM

The Synthetic Users control creates fictional users and orders. Browser-based
synthetic journeys populate OCI APM RUM sessions when the browser runner or
Availability Monitoring script is active.

Show:

1. APM → Real User Monitoring → Web Applications.
2. Open Users / Sessions.
3. Search for a fictional user domain such as `apex.example.test`.
4. Explain page views, AJAX calls, checkout actions, wallet token actions, and
   JavaScript errors if present.

## Captured-data checklist

Before leaving a demo, prove at least one complete event has all these pivots:

- [ ] `Trace ID` in APM Trace Explorer
- [ ] `Trace ID` or `oracleApmTraceId` in OCI Logging / Log Analytics
- [ ] `Order ID` for checkout/storyboard
- [ ] `Payment Gateway Request ID` for payment scenarios
- [ ] `DbOracleSqlId` on at least one SQL span
- [ ] RUM user/session evidence for browser scenarios
- [ ] Java app-server evidence for App Servers scenarios
- [ ] `Attack ID` and MITRE fields for Attack Lab

## Operator evidence center

Use the Admin **Captured Data** page to build copy-paste OCI pivots from any
trace, order, gateway, attack, or assistant key. The page intentionally builds
links and query snippets without exposing credentials or reading private OCI
configuration from the browser.
