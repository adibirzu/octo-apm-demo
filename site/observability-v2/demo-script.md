# Step-by-Step Demo Guide

This guide is the sanitized delivery script for the OCTO observability demo.
Use placeholders in committed documentation. For a private live delivery, load
the real endpoints from ignored deployment files or shell variables:

```bash
export OCTO_LIVE_SHOP_URL="https://shop.example.test"
export OCTO_LIVE_ADMIN_URL="https://admin.example.test"
set -a; . credentials/<profile>/app-secrets.env; set +a
```

Do not commit real tenancy names, live domains, public IP addresses, OCIDs,
wallet paths, passwords, or console account-header screenshots.

## Demo Users

The demo uses fictional corporate users from the synthetic identity domain
`apex.example.test`. The VM timer and the Admin **Synthetic Users** control
create or refresh the same pool:

| Name | User e-mail | Persona |
| --- | --- | --- |
| Alex Chen | `alex.chen@apex.example.test` | Fleet operations buyer |
| Maya Ionescu | `maya.ionescu@apex.example.test` | Field services buyer |
| Nora Patel | `nora.patel@apex.example.test` | Energy survey buyer |
| Daniel Rossi | `daniel.rossi@apex.example.test` | Infrastructure buyer |
| Irina Marin | `irina.marin@apex.example.test` | Public safety buyer |
| Samuel Wright | `samuel.wright@apex.example.test` | Logistics buyer |
| Elena Garcia | `elena.garcia@apex.example.test` | Agriculture buyer |
| Noah Kim | `noah.kim@apex.example.test` | Inspection buyer |
| Sofia Andersen | `sofia.andersen@apex.example.test` | Rail systems buyer |
| Matei Popa | `matei.popa@apex.example.test` | Utilities buyer |
| Lina Hoffman | `lina.hoffman@apex.example.test` | Emergency response buyer |
| Omar Saleh | `omar.saleh@apex.example.test` | Maritime buyer |

For browser/RUM demos, open the shop with one user at a time:

```text
${OCTO_LIVE_SHOP_URL}/shop?synthetic_user=maya.ionescu@apex.example.test
```

The RUM bootstrap stores the e-mail in browser local storage as
`octoSyntheticUserEmail` and sets `window.apmrum.username` before the OCI RUM
browser agent loads.

Admin local login uses the generated deployment credentials:

| Field | Value |
| --- | --- |
| Username | `BOOTSTRAP_ADMIN_USERNAME` from `credentials/<profile>/app-secrets.env`; default is `admin` |
| Password | `BOOTSTRAP_ADMIN_PASSWORD` from `credentials/<profile>/app-secrets.env` |

Never paste the password into documentation, screenshots, issues, or commits.

## 1. Open The Shop

1. Open `${OCTO_LIVE_SHOP_URL}/shop?synthetic_user=maya.ionescu@apex.example.test`.
2. Confirm the catalog renders with live products from ATP.
3. Confirm the page header shows RUM/APM indicators when those services are configured.
4. Search or filter the catalog if needed, then open product details for one drone.
5. Add two drone products to the cart.

Expected telemetry:

- RUM page view for `/shop`.
- RUM custom actions for catalog load, add to cart, and checkout preparation.
- Shop API spans for `/api/shop/storefront`, `/api/products`, and cart actions.

## 2. Buy With A Dummy Card

Use only dummy payment data. The simulator stores card brand, last four digits,
expiry metadata, fingerprint, status, risk score, and gateway request id; it
does not persist or log full PAN or CVV.

1. Fill in checkout details:
   - Contact name: `Maya Ionescu`
   - Contact e-mail: `maya.ionescu@apex.example.test`
   - Company: `Apex Field Services`
   - Phone: `+1 555 0184`
   - Shipping address: `100 Demo Operations Way`
2. Select **Credit Card**.
3. Use a successful dummy VISA:
   - Card number: `4111111111111111`
   - Expiry: a future value such as `12/30`
   - CVV: `123`
   - Postal code: `10001`
4. Click **Place Order** once.
5. Copy the returned order id and trace id if the UI shows them.

Expected telemetry:

- RUM action `shop.checkout_start`.
- Shop span `shop.checkout`.
- Payment spans around `payment.simulated.authorize`.
- Java app-server spans for quote, payment authorization, or verification when
  the sidecar is configured.
- SQL spans for customer, order, order items, payment transaction, and CRM sync.
- App logs with `oracleApmTraceId`, `oracleApmSpanId`, `payment.status`,
  `payment.gateway.request_id`, and `orders.order_id`.

## 3. Simulate Other Payment Methods

Repeat checkout with a different fictional user and method for each scenario.
Use one browser tab or profile per user when you want clean RUM sessions.

| Method | User | Steps | Expected result |
| --- | --- | --- | --- |
| Mastercard | `alex.chen@apex.example.test` | Select **Credit Card**, use `5555555555554444`, future expiry, CVV `321`. | Authorized payment with `payment.card_brand=mastercard`. |
| Issuer decline | `nora.patel@apex.example.test` | Select **Credit Card**, use `4000000000000002`, future expiry, CVV `123`. | Declined/review path with antifraud reason and same trace context. |
| Apple Pay | `irina.marin@apex.example.test` | Select **Apple Pay (simulated)**, click **Simulate Apple Pay**, then place order. | Tokenized wallet path with `payment.wallet_type=apple_pay`. |
| Google Pay | `samuel.wright@apex.example.test` | Select **Google Pay (simulated)**, click **Simulate Google Pay**, then place order. | Tokenized wallet path with `payment.wallet_type=google_pay`. |
| Bank transfer | `daniel.rossi@apex.example.test` | Select **Bank Transfer (Net 30)**, then place order. | Manual/offline payment path with `payment.method=bank_transfer`. |

Use these methods to show payment gateway observability:

- payment provider and method distribution
- successful versus declined gateway decisions
- tokenized wallet fields without raw wallet tokens
- Java app-server verification status
- ATP payment transaction rows
- app logs that drill back to the same APM trace

## 4. Create A Support Ticket

1. Open `${OCTO_LIVE_SHOP_URL}/services?synthetic_user=maya.ionescu@apex.example.test`.
2. Click **Book** on a service card if you want the form pre-filled.
3. Submit a ticket such as `Need telemetry validation for order <order-id>`.
4. Confirm the ticket appears in the open-ticket list.

Expected telemetry:

- RUM page view for `/services`.
- Service API spans for `/api/services/catalog` and `/api/services/tickets`.
- CRM integration spans when the support path is linked to CRM.
- Logs with the same fictional user, request id, and trace context.

## 5. Run Admin Controls

1. Open `${OCTO_LIVE_ADMIN_URL}/login`.
2. Sign in with the generated local admin account from
   `credentials/<profile>/app-secrets.env`.
3. Open `${OCTO_LIVE_ADMIN_URL}/settings`.
4. Run **Java Health** to validate the Java app-server APM path.
5. Run **Demo Storyboard** to create a linked shop, payment, support, Java,
   SQL, and log path.
6. Run **Synthetic Users** if the card is visible; otherwise confirm the VM
   timer is active.
7. Run **Generate Attack** only when you are ready to explain the cyber
   investigation flow.
8. Copy the returned `trace_id`, `attack_id`, order id, payment id, and ticket
   id when shown.

The actual backend routes are:

| UI action | Route |
| --- | --- |
| Java health | `/api/shop/app-server/health` |
| Java scenario | `/api/shop/app-server/simulate/{scenario}` |
| Payment scenario | `/api/shop/payment/simulate/{scenario}` |
| Demo Storyboard | `/api/shop/demo/storyboard` |
| Attack Lab | `/api/shop/attack/simulate` |
| Synthetic Users | `/api/synthetic/users/run` |
| 360 Monitoring | `/api/observability/360` |
| Payment gateway events | `/api/observability/payment-gateway/events` |

## 6. Open OCI APM Home And Service Monitoring

Console path:

```text
OCI Console -> Observability & Management -> Application Performance Monitoring
```

Select the correct compartment and APM domain for the demo. Start with the APM
Home dashboard and explain each widget:

| Widget | What to show |
| --- | --- |
| Services | Active application services in the APM domain; expect only the configured shop, admin/CRM, Java app-server, and database service names for this deployment. |
| Traces | Recent trace count, error traces, and slow traces. Use this as the bridge into Trace Explorer. |
| Web applications | RUM web apps for the shop/admin frontends. Use this to move into RUM. |
| Application servers | Java app-server resource health and JVM/app-server metrics. Use this to open App Servers. |
| Monitors | Availability monitors, recent runs, and failed run count. Use this to open Availability Monitoring. |
| Alarms | APM/Monitoring alarms that fired in the selected time window. |

Then open **Service Monitoring** or the **Services** widget:

1. Select the shop service.
2. Review request count, average response time, errors, Apdex, and endpoint
   breakdown.
3. Drill into the checkout endpoint and note latency/error contribution.
4. Move to the admin/CRM service and compare request volume and error rate.
5. Move to the Java app-server service and identify Java verification or
   simulation endpoints.
6. Open a slow/error trace from the service details page.

Use the service view to explain that service widgets aggregate many traces,
while Trace Explorer explains one exact request.

## 7. Trace Explorer: Follow One Order End To End

Console path:

```text
OCI Console -> Observability & Management -> Application Performance Monitoring -> Trace Explorer
```

1. Set the time window around the checkout you performed.
2. Search by copied `trace_id`, or filter by:

```text
workflow.id = 'checkout' OR payment.gateway.request_id exists
```

3. Open the trace details.
4. Explain the span waterfall in order:
   - Browser/RUM page or action span.
   - Load Balancer/WAF/API Gateway simulated edge evidence where present.
   - Shop server span.
   - Catalog or product lookup spans.
   - Checkout validation span.
   - Payment gateway receipt, antifraud, Java app-server, and authorization spans.
   - CRM order-sync spans.
   - SQL spans to ATP for customer, order, order item, payment transaction, and support ticket writes.
5. Open the payment span and show `payment.method`, `payment.status`,
   `payment.risk_score`, `payment.gateway.request_id`, and wallet/card-safe
   metadata.
6. Open a SQL span and show `db.system`, `db.operation`, `db.statement` or
   preview, and `DbOracleSqlId` when present.
7. Use `oracleApmTraceId` to pivot to app logs in OCI Logging or Log Analytics.

## 8. App Servers: JVM And Process Visibility

Console path:

```text
OCI Console -> Observability & Management -> Application Performance Monitoring -> App Servers
```

1. Select the Java app-server resource for the deployment.
2. Set the time window around the Demo Storyboard, payment checkout, or Java
   simulation.
3. Check:
   - Heap used and heap utilization.
   - Process CPU usage.
   - Garbage collection activity.
   - Threads or request load where visible.
   - Server requests, errors, and response time.
4. Open service requests from the app-server page and pivot back to the trace
   that includes the checkout or attack simulation.
5. If the page is empty, confirm the Java sidecar is running with OCI APM Java
   agent flags that mark it as an app server, then regenerate Java Health.

## 9. RUM: User Sessions And Web Applications

Console path:

```text
OCI Console -> Observability & Management -> Application Performance Monitoring -> Real User Monitoring
```

1. Select the shop web application.
2. Review Apdex, page response time, page views, AJAX calls, JavaScript errors,
   operating systems, browsers, and geography widgets.
3. Open **Users** and search for a fictional user such as
   `maya.ionescu@apex.example.test`.
4. Drill into the user session and show the sequence:
   - shop page load
   - product detail or add-to-cart action
   - checkout start
   - wallet token creation if Apple Pay/Google Pay was used
   - checkout completion or decline
   - support page load and ticket submission
5. Switch to the admin web application and show the Admin Storyboard or Attack
   Lab session.
6. Explain custom dimensions:
   - `synthetic_user_enabled`
   - `synthetic_user_domain`
   - request/workflow attributes where present

Use RUM to explain user experience. Use Trace Explorer to explain the backend
path for the same browser session.

## 10. Availability Monitoring

Console path:

```text
OCI Console -> Observability & Management -> Application Performance Monitoring -> Availability Monitoring
```

1. Open the monitors dashboard.
2. Show availability percentage for the shop and admin readiness monitors.
3. Explain vantage points: each monitor run executes from selected global
   locations so the team can see regional failures and latency differences.
4. Click a shop monitor.
5. Review monitor information, target URL, interval, timeout, SSL validation,
   DNS override status, and selected vantage points.
6. Open **History**.
7. Filter to the demo time window.
8. Click a monitor run and show:
   - status and completion time
   - selected vantage point
   - waterfall/HAR details
   - response headers and timings
   - screenshots where available
   - trace details if the monitored app is instrumented in the same APM domain
9. Repeat for the admin monitor and compare availability percentage and
   response time.

To create a scripted browser monitor for the same user path:

1. Open **Scripts** in Availability Monitoring.
2. Create a script of type **Playwright**.
3. Upload `tools/demo-guide/octo-availability-monitor.playwright.ts`.
4. Validate the script from a non-production test target first.
5. Create a **Scripted Browser** monitor from that script.
6. Select the APM domain, interval, timeout, SSL validation, and global vantage
   points.
7. Enable screenshots and HAR collection for troubleshooting.
8. Add the monitor to the runbook dashboard and tag it with the deployment
   prefix.

## 11. Log Analytics Drilldown

Console path:

```text
OCI Console -> Observability & Management -> Log Analytics -> Log Explorer
```

1. Set the time window around the order or attack.
2. Filter by `oracleApmTraceId = <trace_id>` or
   `payment.gateway.request_id = <gateway_request_id>`.
3. Pin these fields:
   - `Trace ID`
   - `Span ID`
   - `Service`
   - `Host Name`
   - `User Name`
   - `Payment Method`
   - `Payment Status`
   - `Payment Gateway Request ID`
   - `MITRE Technique ID`
   - `OSQuery Finding`
   - `Original Log Content`
4. Open an app log row and use the trace id to return to APM Trace Explorer.
5. For the attack story, run:
   - `attack-lab-trace-timeline.sql`
   - `attack-lab-detections.sql`
   - `osquery-attack-findings.sql`
   - `api-gateway-edge-detections.sql`

## 12. Stack Monitoring Resource Discovery

Use Stack Monitoring only after the Management Agent is active and the
deployment has permission to discover resources.

Console path:

```text
OCI Console -> Observability & Management -> Stack Monitoring -> Resource Discovery
```

For each app server host:

1. Click **Discover New Resource**.
2. Set **Resource Type** to **Host**.
3. Set **Resource Name** to the host FQDN used by the deployment, for example
   `<shop-host-fqdn>` or `<admin-host-fqdn>`.
4. Set **Management Agent** to the agent installed on that same host.
5. Select **Stack Monitoring and Log Analytics** so discovery sends resource
   context to both services.
6. Select **Enterprise Edition** unless the deployment explicitly requires
   Standard Edition.
7. Expand **Show advanced options** only when you need tags or custom
   properties.
8. Click **Discover New Resource**.
9. Wait for the discovery job to finish.
10. Open the host resource details and verify CPU, memory, filesystem, process,
    and availability metrics.

Repeat for the admin host. Do not type or commit real live hostnames in public
docs; use ignored private runbooks or environment variables for live delivery.

## 13. Close The Story

Use this narrative:

1. A fictional user opened the shop, added drones, and paid with a dummy method.
2. RUM proves the browser session and user actions.
3. Service Monitoring proves service-level latency and errors.
4. Trace Explorer proves the exact request path from browser to shop, Java,
   payment gateway simulation, CRM, and ATP SQL.
5. App Servers proves Java heap, CPU, and server-request behavior for the Java
   sidecar.
6. Log Analytics proves structured app/security/payment/OS logs for the same
   trace id.
7. Availability Monitoring proves whether global vantage points saw the same
   symptom.
8. Stack Monitoring and DB Management/Operations Insights explain host and DB
   health for the same time window.

## Supporting Scripts

The frontend-only Playwright script for Availability Monitoring and local
browser validation is:

```text
tools/demo-guide/octo-availability-monitor.playwright.ts
```

The existing local browser runner remains useful for private traffic
generation:

```bash
cd services/browser-runner
OCTO_BROWSER_SHOP_URL="${OCTO_LIVE_SHOP_URL}" \
OCTO_BROWSER_CRM_URL="${OCTO_LIVE_ADMIN_URL}" \
OCTO_BROWSER_SYNTHETIC_USER_DOMAIN=apex.example.test \
OCTO_BROWSER_ITERATIONS=5 \
npx tsx src/run-journey.ts catalog-to-checkout
```

## Official OCI References

- OCI Application Performance Monitoring:
  <https://docs.oracle.com/en-us/iaas/application-performance-monitoring/home.htm>
- Trace Explorer:
  <https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-trace-explorer.html>
- APM Browser Agent and RUM:
  <https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-browser-agent-real-user-monitoring.html>
- Availability Monitoring scripts:
  <https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-script.html>
- Availability Monitoring monitors:
  <https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html>
- Monitor history, HAR, screenshots, and trace details:
  <https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/view-monitor-history.html>
- OCI Log Analytics:
  <https://docs.oracle.com/en-us/iaas/log-analytics/home.htm>
- Ingest OCI service logs into Log Analytics with Service Connector:
  <https://docs.oracle.com/en-us/iaas/log-analytics/doc/ingest-logs-other-oci-services-using-service-connector.html>
- OCI Stack Monitoring resource discovery:
  <https://docs.oracle.com/en-us/iaas/stack-monitoring/doc/promotion-and-discovery.html>
