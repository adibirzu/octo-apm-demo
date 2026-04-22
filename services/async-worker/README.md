# octo-async-worker

Redis-Streams consumer. Gives the platform an **asynchronous** execution
path alongside the synchronous shop→CRM order POST — retries + DLQ +
consumer-group scale-out + full APM instrumentation for the async
boundary.

## Why async?

The synchronous path today: shop `/api/orders` POSTs directly to CRM
`/api/orders` inline with the customer request. If CRM is slow or
down, the customer sees it. Shop's circuit breaker mitigates, not
eliminates.

The async path: shop XADDs an event to `octo.orders.to-sync`, returns
200 to the customer immediately, and this worker processes the event
within seconds. CRM flakiness no longer stops checkouts.

Both paths live side-by-side during migration; the shop picks which
path to use via config.

## Streams + handlers

| Stream | Handler | Purpose |
|---|---|---|
| `octo.orders.to-sync` | `handlers/order_sync.py` | POSTs the order to CRM with idempotency + trace propagation |

Add a handler: drop a module in `src/octo_async_worker/handlers/`
exporting `async def handle(event)`, then register in
`handlers/__init__.py:HANDLERS`.

## Event wire format

Written by `EventPublisher.publish()`, read by `StreamConsumer.poll()`:

```
field              value
──────────────────────────────────────────────────────────
payload            JSON blob — handler-specific
run_id             uuid or ""
workflow_id        slug like "async.order-sync"
trace_id           32 hex — producer's W3C trace_id
span_id            16 hex — producer's current span id
delivery_attempt   integer (1 on first publish)
created_at         ISO-8601 UTC
```

`delivery_attempt` increments on each retry. Workers read
`traceparent` from `trace_id`+`span_id` to propagate the trace into
their handler spans, so the whole async hop joins one trace in APM.

## Retry + DLQ

| Outcome | What happens |
|---|---|
| Handler returns normally | `XACK` — message is gone |
| Handler raises `NonRetriableError` | DLQ immediately (no retries) |
| Handler raises anything else | Retry: XADD back with `delivery_attempt+1`, XACK original |
| After `max_delivery_attempts` retries | DLQ with `dlq_reason=max-attempts-exceeded` |

The DLQ is `<stream>.dlq`. It's **just another stream** — start a
second worker targeting `octo.orders.to-sync.dlq` with a repair
handler, or drain it by hand via `XRANGE`.

## Scale-out

Consumer groups are the built-in Redis mechanism. Two pods with the
same `OCTO_WORKER_CONSUMER_GROUP` but different `OCTO_WORKER_CONSUMER_NAME`
(default: pod name via downward API) will split the stream between
them — each message is delivered to exactly one consumer.

HPA scales the Deployment 2→8 replicas on CPU. Because each consumer
group name is stable (`octo-async-worker`), scaling in doesn't drop
messages — pending entries are XCLAIM-able by survivors (future
work: KG-033 implements pending-list recovery).

## Run

### Local dev

```bash
cd services/async-worker
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

OCTO_WORKER_REDIS_URL=redis://localhost:6379 \
OCTO_WORKER_CRM_BASE_URL=http://localhost:8081 \
octo-async-worker
```

### K8s

```bash
docker build -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-async-worker:latest .
docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-async-worker:latest

OCIR_REGION=… OCIR_TENANCY=… IMAGE_TAG=latest \
envsubst < k8s/deployment.yaml | kubectl apply -f -
```

### Tests

```bash
python -m pytest -q
# 9 passed — no network needed (fakeredis in-process)
```

Coverage:
- Publish → poll round-trip
- ACK removes the message from re-delivery
- Retry increments `delivery_attempt`
- DLQ after max attempts
- `ensure_groups()` is idempotent
- Worker processes happy path + retriable + non-retriable + unhandled-stream

## How the shop uses it

The shop's order route POSTs synchronously today; a follow-up
(KG-034) adds the async fan-out via `EventPublisher.publish()` with a
feature flag so both paths are available during migration. Rough
signature:

```python
from octo_async_worker import EventPublisher

async def sync_order_to_crm(order_id: int, ...):
    if cfg.async_order_sync_enabled:
        await publisher.publish(
            stream="octo.orders.to-sync",
            payload={"order_id": order_id, "customer_id": ..., ...},
            run_id=cfg.current_run_id or "",
            workflow_id="shop.order.sync",
            trace_id=current_span.trace_id_hex,
            span_id=current_span.span_id_hex,
        )
        return {"queued": True}
    # ... existing sync path ...
```

## Follow-up KG tickets

- **KG-033**: pending-list recovery via XCLAIM for crashed consumers.
- **KG-034**: shop checkout optional async fan-out with feature flag.
- **KG-035**: DLQ UI in the CRM Ops portal so operators can browse +
  retry + drop dead-lettered events without Redis CLI access.
