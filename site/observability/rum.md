# Real User Monitoring (RUM)

OCI APM RUM agent is injected into the browser via `base.html` when `rum_configured=True`.

## Configuration

```javascript
window.apmrum = {
  serviceName: "octo-drone-shop",
  webApplication: "octo-drone-shop-web",
  ociDataUploadEndpoint: "<rum-endpoint>",
  OracleAPMPublicDataKey: "<public-data-key>"
}
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

## Session Correlation

- RUM sessions linked to backend traces via `trace_id`
- Session ID stored in `localStorage` as `octo-session-id`
- Correlation visible in OCI APM → RUM → Session Explorer

## Verification

1. **OCI APM** → Real User Monitoring → Session Explorer
2. Filter by `shop.add_to_cart` or `shop.checkout_complete`
3. Click a session to see the full user journey with correlated backend traces
