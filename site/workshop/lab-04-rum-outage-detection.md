# Lab 04 — Detecting a frontend outage from RUM

## Objective

Use OCI APM Real User Monitoring (RUM) to detect when the frontend is
broken from the customer's perspective — even when the backend
`/ready` says everything is fine.

## Time budget

25 minutes.

## Prerequisites

- Lab 01 complete.
- RUM Web Application provisioned in your APM Domain
  (`deploy/oci/ensure_apm.sh --apply` does this).
- A modern browser (we'll use the dev tools).

## Steps

### 1. Open the shop in your browser

```
https://shop.example.tld
```

Open dev tools → Network tab. Reload. You should see a request to
`https://...oci.oraclecloud.com/.../rum/...` — that's the RUM SDK
beacon. The Web Application ID embedded in the beacon URL must match
your `OCI_APM_WEB_APPLICATION` value.

### 2. Trigger a journey

1. Browse to a product page.
2. Add to cart.
3. Open the cart panel.

Each interaction sends a beacon. With dev tools open, you should see
~3-5 beacon POSTs.

### 3. Find your session in RUM (Console)

Console → APM → **Real User Monitoring → Sessions Explorer**.

Filter by:
- Time range: last 5 minutes
- Web Application: your RUM app

Sessions are listed newest-first. Click yours (look for the user-agent
matching your browser).

### 4. What you can see

Each session shows:

- **Session timeline** — page loads, route changes, custom events
  emitted by the shop (`shop.add_to_cart`, `shop.checkout_complete`,
  etc.).
- **Performance metrics** — Time to First Byte, Time to Interactive,
  CLS, INP — captured per page.
- **Errors** — any `console.error` or unhandled promise rejection.
- **Network** — every `fetch`/`XHR` made by the page; failures
  highlighted.

### 5. Simulate a failure

In dev tools console, run:

```js
// Force a fetch error
fetch('https://shop.example.tld/api/intentionally-missing')
    .then(r => r.json())
    .catch(e => console.error('lab-04 forced error', e));
```

Within 30 s, refresh the Sessions Explorer. Your session should now
show:

- A **failed network request** (404).
- A **JavaScript console error** (`lab-04 forced error`).

### 6. Pivot from RUM session to backend trace

Click the failed network request in the session timeline. The right
panel shows:

- Request URL + method.
- HTTP status.
- A `traceparent` header that the SDK injected (look at "Headers sent
  by browser").
- A link "View server-side trace" → opens APM Trace Explorer for that
  exact `trace_id`.

That's the missing pivot in most observability setups: RUM session →
specific backend trace, in one click.

## Verify

```bash
./tools/workshop/verify-04.sh
```

The verifier polls RUM Sessions Explorer for any session in the last
5 minutes with at least one error event.

```
✓ RUM Web Application configured (OCI_APM_WEB_APPLICATION not empty)
✓ at least one RUM session in the last 5 minutes
✓ at least one session contains an error event
PASS — Lab 04 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No RUM beacon in browser network tab | RUM SDK not injected | Check `shop/server/templates/base.html` — the `<script>` tag using `OCI_APM_RUM_ENDPOINT` should be present in the rendered HTML |
| Beacons fire but Sessions Explorer empty | Wrong `OCI_APM_WEB_APPLICATION` ID | The embedded ID in the beacon URL must match the Web App OCID in your APM Domain config |
| Custom events (`shop.add_to_cart`) missing | Custom-event hook not wired | Look at `shop/static/js/observability.js` — should call `window.apmrum.recordEvent('shop.add_to_cart', { …})` |

## Read more

- [Observability → RUM](../observability/rum.md)
- [APM RUM Web SDK reference](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/web-application.html)

---

[← Lab 03](lab-03-slow-sql-drill-down.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 05 → Custom metric + alarm →](lab-05-metric-and-alarm.md)
