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

## Wire up to the FastAPI app

In `shop/server/main.py`:

```python
from server.modules.payments.webhooks import router as payments_webhooks_router
app.include_router(payments_webhooks_router)
```

## Configure (Stripe example)

```bash
export PAYMENT_PROVIDER=stripe
export STRIPE_API_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
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
# 15 passed in ~0.03s — no network
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
