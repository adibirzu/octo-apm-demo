# Real User Monitoring (RUM)

OCI APM RUM agent is injected into the browser via `base.html` when `rum_configured=True`.
The CRM and Shop pages both propagate same-origin browser calls with W3C trace
context so APM can connect RUM sessions to backend HTTP spans and ATP SQL
spans.

## Configuration

```javascript
window.apmrum = {
  serviceName: "octo-drone-shop",
  webApplication: "octo-drone-shop-web",
  ociDataUploadEndpoint: "<rum-endpoint>",
  OracleAPMPublicDataKey: "<public-data-key>"
}

window.apmrum.traceSupportingEndpoints = [
  { hostPattern: "<current-host>", headers: ["W3C"] }
]
```

## Custom RUM Events

| Event | When | Attributes |
|---|---|---|
| `shop.page_loaded` | Page load complete | load_time_ms, product_count |
| `shop.search` | Product search | query, category, sort |
| `shop.add_to_cart` | Item added to cart | product_id, name, price, category, cart_size |
| `shop.checkout_start` | Checkout initiated | cart_items, cart_total, session_id |
| `shop.checkout_complete` | Order placed | order_id, total, tracking_number |
| `shop.checkout_error` | Checkout failed | error_message, cart_items |
| `shop.page_load_error` | Page load failure | error_details |
| `auth.login.submit` | CRM login submitted | auth_method |
| `auth.login.result` | CRM login completed | status, role on success |
| `ui.click` | CRM admin/control click | action, control, admin_lab_card |

Login RUM events are deliberately sanitized: they do not include usernames,
passwords, tokens, or email addresses. User-to-order correlation happens through
the authenticated backend session, request spans, audit records, and database
relations.

## Session Correlation

- RUM sessions linked to backend traces via `trace_id`
- Session ID stored in `localStorage` as `octo-session-id`
- Correlation visible in OCI APM → RUM → Session Explorer
- CRM login and admin Coordinator requests can be followed from RUM actions to
  `/api/auth/login` or `/api/admin/coordinator/query`, then to DB spans and
  structured logs with `trace_id` / `oracleApmTraceId`.

## Verification

1. **OCI APM** → Real User Monitoring → Session Explorer
2. Filter by `shop.add_to_cart` or `shop.checkout_complete`
3. Click a session to see the full user journey with correlated backend traces
