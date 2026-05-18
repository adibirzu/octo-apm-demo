# Synthetic Monitoring

The canonical OCI APM Scripted Browser journey is:

```text
shop/tools/apm/octo-apm-demo-synthetic.spec.ts
```

It is designed for APM Availability Monitoring and for local Playwright
validation. The script has two modes:

| Mode | Purpose | Path |
|---|---|---|
| `monitor` | Recurring monitor | 12 fictional buyers, 2-3 drones each, mixed card/wallet/bank-transfer payments, support ticket, admin login, Java health, attack lab |
| `full` | Workshop or demo setup | full payment matrix, admin storyboard, and synthetic-user generation |

The legacy facilitator script remains available at
`tools/demo-guide/octo-availability-monitor.playwright.ts`, but new
deployment automation should upload the canonical script above.

## Synthetic Buyers

The recurring buyer path uses these fictional users. Each checkout buys 2 or
3 in-stock drones and rotates across approved Visa, approved Mastercard,
issuer-declined Visa, Apple Pay, Google Pay, and bank transfer.

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

## Safe Parameters

Do not commit live URLs, passwords, Vault OCIDs, or internal service keys.
Configure them at deployment time:

```text
OCTO_LIVE_SHOP_URL=https://shop.example.test
OCTO_LIVE_ADMIN_URL=https://admin.example.test
OCTO_APM_DEMO_MODE=monitor
OCTO_ADMIN_USERNAME=admin
OCTO_ADMIN_PASSWORD=<secret monitor parameter>
OCTO_INTERNAL_SERVICE_KEY=<optional secret monitor parameter>
```

For OCI monitors, prefer a Vault-backed password parameter on the operator
machine:

```text
OCTO_ADMIN_PASSWORD_SECRET_OCID=<ADMIN_PASSWORD_SECRET_OCID>
OCTO_ADMIN_PASSWORD_SECRET_REGION=<OCI_REGION>
OCTO_ADMIN_PASSWORD_SECRET_AUTH=RESOURCE_PRINCIPAL
```

The deploy helper converts that to an OCI synthetic secret parameter in a
temporary local JSON file. It does not print the secret value or write it to
the repo.

## Deployment Flow

Dry-run the REST readiness monitors and the Scripted Browser monitor:

```bash
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
SYNTHETIC_BROWSER_MONITOR_ENABLED=true \
./deploy/oci/ensure_availability_monitors.sh --dry-run
```

Create or update the monitors:

```bash
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
SYNTHETIC_BROWSER_MONITOR_ENABLED=true \
OCTO_LIVE_SHOP_URL=https://shop.example.test \
OCTO_LIVE_ADMIN_URL=https://admin.example.test \
OCTO_ADMIN_PASSWORD_SECRET_OCID=<ADMIN_PASSWORD_SECRET_OCID> \
OCTO_ADMIN_PASSWORD_SECRET_REGION=<OCI_REGION> \
./deploy/oci/ensure_availability_monitors.sh --apply
```

Scripted Browser defaults are `repeat=600`, `timeout=300`,
`isFailureRetried=false`, and `OCTO_APM_DEMO_MODE=monitor`. URL parameters
are non-secret. The admin password and optional internal service key are
secret parameters.

## Local Validation

For a local stack:

```bash
cd shop
OCTO_LIVE_SHOP_URL=http://localhost:8080 \
OCTO_LIVE_ADMIN_URL=http://localhost:8081 \
OCTO_ADMIN_PASSWORD=<ADMIN_PASSWORD> \
OCTO_APM_DEMO_MODE=monitor \
npm run test:e2e:synthetic-apm
```

Set `OCTO_INTERNAL_SERVICE_KEY` only when you want the script to call
`/api/observability/payment-gateway/events` and verify the gateway event rows
in the database. Without that key, the checkout still validates the response
payload and the app still emits payment gateway spans/logs.

## Expected Correlation

Each checkout must return and emit:

| Signal | Required fields |
|---|---|
| RUM | `apmrum.username` for the fictional synthetic user, plus `synthetic_user_enabled` and `synthetic_user_domain` custom dimensions |
| Checkout response | `trace_id`, `payment_status`, `payment.gateway.request_id` |
| Payment gateway spans/logs | `payment.gateway.request_id`, `payment.method`, `payment.provider`, `payment.network`, `payment.verification.decision`, `payment.risk_score` |
| Gateway event drilldown | `summary.gateway_request_ids`, persisted step names, order payment status |
| Log Analytics | `oracleApmTraceId`, `payment.gateway.request_id`, order/payment fields |

Payment telemetry is token-safe. The synthetic scripts type dummy card data
into the browser, but assertions reject any checkout response that echoes the
full card number or CVV. Spans, logs, CRM rows, and
`payment_gateway_events` must use tokenized metadata such as card brand,
last4, wallet type, risk score, and gateway request id.
