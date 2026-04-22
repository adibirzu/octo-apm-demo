# octo-object-pipeline

OCI Object Storage event → processor → outcome event. Demo use cases:
PDF invoice parsing (`octo-invoices` bucket), catalog image validation
(`octo-catalog-images` bucket).

OCI 360 Phase 4 — object-processing visibility surface.

## Flow

```
Object Storage (createobject) ──► OCI Events ──► POST /events/object-storage
                                                        ↓
                            handler lookup by bucket name
                                                        ↓
                                  fetch object bytes via OS SDK
                                                        ↓
                                       run async handler
                                                        ↓
               emit com.octodemo.object-pipeline.<bucket>.processed event
```

## Handlers

| Bucket | Handler | What it does |
|---|---|---|
| `octo-invoices` | `process_invoice` | Regex-extracts `Total: $X.XX`, emits `invoice.processed` event with amount + currency |
| `octo-catalog-images` | `process_catalog_image` | Size-caps at 5 MB, accepts the upload |

Add a handler: write `async def process(body, metadata) -> ProcessingResult`,
register in `handlers.HANDLERS`, add tests.

## Wire OCI Events

1. Console → Object Storage → bucket `octo-invoices` → **Events** → Enable.
2. Console → Events Service → Create Rule:
   - Event Type: `Object Storage > Object - Create`
   - Condition: bucket name `octo-invoices`
   - Action: Notifications topic `octo-object-pipeline`
3. Notifications subscription: `HTTPS Custom URL` →
   `https://backend.octodemo.cloud/object-pipeline/events/object-storage`
   (through the edge gateway).

## Observability

Every processed object emits a CloudEvent with
`source=octo-object-pipeline` and an event type of
`com.octodemo.object-pipeline.<bucket>.processed`. Consumers filter
by `source`, join to traces via the event's data payload which includes
the `object_name`.

## Tests

```bash
cd services/object-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
# 8 passed
```

Coverage: invoice total extraction, miss-cleanly, image size cap,
image accept, health lists handlers, event processing round-trip with
injected fetch_object, unknown bucket returns no-handler, malformed
event → 400.
