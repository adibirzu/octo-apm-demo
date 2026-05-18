# Payment Gateway — Phase 2

Provider-neutral payment abstraction. One active provider per
deployment, selected via `PAYMENT_PROVIDER=stripe|paypal|oci_osb`.
Absent or unknown values fall back to the legacy stubbed total so
existing demos keep working.

## Pieces

| Module | Role |
|---|---|
| `base.py` | `PaymentProvider` Protocol, `Intent`, `WebhookEvent`, `PaymentEventKind` canonical enum, `InvalidSignature` exception |
| `state_machine.py` | `OrderState` + `transition()` — enforces legal edges, rejects shortcuts |
| `stripe_provider.py` | Stripe adapter (PaymentIntent + construct_event) |
| `paypal_provider.py` | PayPal scaffold (prod impl in follow-up PR) |
| `oci_osb_provider.py` | OCI Subscription Billing scaffold |
| `registry.py` | Env-driven singleton picker with `*_FILE` secret support |
| `webhooks.py` | `POST /api/payments/webhooks/{provider}` — verifies, classifies, transitions state, emits OCI Event |
| `events.py` | Fire-and-forget POST to OCI Events on every state change |
| `gateway_emulator.py` | Dedicated payment gateway emulator between checkout and processor; emits per-step spans/logs and stores token-safe gateway events |
| `checkout_workflow.py` | Normalizes card/wallet payloads into PCI-safe metadata, risk reasons, and persistence fields |

## Enterprise Demo Gateway Trace

The shop checkout path runs a dedicated gateway emulator for
`credit_card`, `apple_pay`, and `google_pay`. Each payment creates a
gateway request id, spans, structured logs, and `payment_gateway_events`
rows for these phases:

1. Gateway ingress and card/wallet token handling.
2. Internal gateway antifraud screening.
3. Antifraud verification app request/response through the Java APM
   sidecar (`/api/java-apm/payment/verify`).
4. Simulated processor authorization through the Java APM sidecar
   (`/api/java-apm/payment/authorize`).
5. Simulated Visa/Mastercard network routing, with response code,
   gateway code, AVS/CVV result, 3DS indicator, retrieval reference,
   and synthetic network transaction id.
6. Normalized merchant authorization result returned to Drone Shop.

APM component attributes are explicit on every gateway span, so the
Topology/Trace Explorer component column separates wallet, processor, and
network work:

| Span phase | `component` |
|---|---|
| Google Pay wallet/token phases | `google-pay-gateway` |
| Apple Pay merchant session/token phases | `apple-pay-gateway` |
| Antifraud verification app | `octo-antifraud-verification-app` |
| Java processor request/response | `octo-java-payment-processor` |
| Visa authorization rail | `visa-payment-network` |
| Mastercard authorization rail | `mastercard-payment-network` |

The flow is modeled after the public wallet/card gateway contracts:

| Method | Simulated technical shape | Token-safe evidence emitted |
|---|---|---|
| Google Pay | `PaymentData.paymentMethodData.type=CARD`, `tokenizationData.type=PAYMENT_GATEWAY`, gateway merchant routing, and network-token cryptogram validation | `payment.google_pay.*`, `payment.wallet.token_hash`, gateway name, card network, 3DS attributes |
| Apple Pay | merchant validation, payment token envelope, `paymentData.version=EC_v1`, token header fields, payment method network, and PSP decryption handoff | `payment.apple_pay.*`, token hash, merchant identifier hash, network, 3DS attributes |
| Visa card | e-commerce card tokenization, Visa Secure frictionless simulation, AVS/CVV result, authorization response | `payment.card.*`, `payment.3ds.program=Visa Secure`, `payment.3ds.eci=05`, network response/gateway code |
| Mastercard card | e-commerce card tokenization, Mastercard Identity Check simulation, AVS/CVV result, authorization response | `payment.card.*`, `payment.3ds.program=Mastercard Identity Check`, `payment.3ds.eci=02`, network response/gateway code |

The Java sidecar is part of the payment path, not a detached load demo.
The Python gateway sends only token-safe context to the sidecar:
`payment_gateway_request_id`, method, network, gateway provider, wallet
token hash, card brand/last4, card fingerprint, billing postal-code
presence, CVV presence, risk reasons, and verification decision. The
sidecar enriches the active Java APM span and emits events such as:

- `java.payment.antifraud.verify`
- `java.payment.wallet.google.payment_data.validated`
- `java.payment.wallet.apple.payment_token.validated`
- `java.payment.processor.authorization_request`
- `java.payment.network.visa.authorize`
- `java.payment.network.mastercard.authorize`

Orders start as `payment_pending` with `payment_required=1`. Authorized
payments move the order to `status=paid`, `payment_status=paid`,
`payment_required=0`, and set `payment_paid_at`. Declines, timeouts, and
failures leave the order in `payment_pending` with
`payment_status=failed` and `payment_required=1`.

Known decline test cards:

- Visa: `4000000000000002`
- Mastercard: `5105105105105100`

Only token hashes, card brand/last4, expiry, risk reasons, gateway step
names, trace ids, and provider references are stored. PAN, CVV, and raw
wallet tokens must not be persisted or logged.

## Wire up to the FastAPI app

In `shop/server/main.py`:

```python
from server.modules.payments.webhooks import router as payments_webhooks_router
app.include_router(payments_webhooks_router)
```

## Configure (Stripe example)

```bash
export PAYMENT_PROVIDER=stripe
export STRIPE_API_KEY=<stripe-api-key>
export STRIPE_WEBHOOK_SECRET=<stripe-webhook-secret>
# Optional — emit OCI Events on state changes
export OCI_EVENTS_TOPIC_URL=https://events.<region>.oci.oraclecloud.com/20191108/events/<topic>
```

All three are read via `_env_secret()` which also honours
`STRIPE_API_KEY_FILE` et al — point at a Kubernetes Secret mount or
OCI Vault CSI file.

## State machine

```
        ┌──► cancelled
pending ─┤
        └──► payment_pending ──► paid ──► refunded
                              ├─► failed
                              └─► cancelled
```

Legal transitions live in `_LEGAL_TRANSITIONS` in
`state_machine.py`. Attempting anything else raises
`IllegalTransition`. Self-transitions are no-ops so duplicate webhook
deliveries are idempotent.

## OCI Events emission

Every successful transition posts this CloudEvents-shaped payload to
`OCI_EVENTS_TOPIC_URL`:

```json
{
  "eventType": "com.octodemo.drone-shop.order.paid",
  "eventTypeVersion": "1.0",
  "source": "octo-drone-shop",
  "eventTime": "2026-04-22T19:45:12.345Z",
  "data": {
    "order_id": 100,
    "previous_state": "payment_pending",
    "new_state": "paid",
    "amount_minor_units": 4999,
    "currency": "usd",
    "payment_provider": "stripe",
    "payment_provider_reference": "pi_abc123",
    "oracleApmTraceId": "1a2b3c..."
  }
}
```

The Coordinator subscribes to `com.octodemo.drone-shop.order.failed`
for auto-remediation workflows (e.g. kick off a retry suggestion when
the failure rate exceeds the SLO).

## Tests

```bash
cd shop
python -m pytest tests/payments/ -q
python -m pytest tests/test_checkout_payment_widget.py tests/payments/ -q
npm run test:e2e:payments -- --project=chromium
```

Covered:
- `test_payment_base.py`: Intent is frozen, canonical event kinds
  present, `InvalidSignature` raisable, raw payload preserved.
- `test_order_state_machine.py`: happy path, payment failed branch,
  refund only from paid, cancel only from pending/payment_pending,
  terminal states reject further transitions, direct `pending→paid`
  rejected.
- `test_stripe.py`: create_intent returns client_secret; webhook with
  forged signature raises `InvalidSignature`; `payment_intent.succeeded`
  maps to `SUCCEEDED`; `payment_intent.payment_failed` → `FAILED`;
  unknown event types → `PENDING`.

## Follow-ups tracked as KG tickets

- KG-020: PayPal production implementation (verify-webhook-signature
  REST call, /v2/checkout/orders create).
- KG-021: OCI OSB production implementation (request-signed REST).
- KG-022: Add `payment_provider_reference` index to the Order table
  for O(1) webhook lookup (currently linear scan).
