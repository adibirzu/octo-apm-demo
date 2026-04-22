# octo-browser-runner

Playwright-based journey runner. Drives real Chromium sessions through
shop + CRM flows so **RUM captures real user timings** and APM traces
include the full browser-to-backend chain. Replaces the synthetic-RPS
traffic-generator for scenarios where the browser SDK signal matters.

Spec: OCI 360 Phase 3 — `octo-browser-runner`.

## Why

- `octo-traffic-generator` fires `httpx` calls. It gets APM spans, not
  RUM sessions. RUM only exists when a real browser executes the page.
- The unified VM/OKE paths already ship the RUM SDK baked into every
  page. All that's missing is a headless browser to actually load it.
- Playwright in a container + Microsoft's Docker base → pre-installed
  Chromium + deps → this becomes a 2-minute workshop exercise instead
  of a fragile CI pipeline.

## Journeys (3)

| Name | Purpose |
|---|---|
| `catalog-to-checkout` | Shop end-to-end: land → browse → cart → checkout. Primary RUM signal generator. |
| `crm-admin-stroll` | CRM operator's read-heavy admin day — 4 page loads. |
| `error-retry-loop` | Intentional 4xx + 5xx + 404 hits — keeps RUM + APM error widgets non-empty during demos. Wires into `app-exception-storm` profile. |

Add a new journey: drop a file in `journeys/NAME.ts` exporting
`runJourney(context, config)`, and add it to the registry in
`src/run-journey.ts`.

## Run locally

```bash
cd services/browser-runner
npm install
npx playwright install chromium

OCTO_BROWSER_SHOP_URL=https://drone.octodemo.cloud \
OCTO_BROWSER_CRM_URL=https://backend.octodemo.cloud \
OCTO_BROWSER_ITERATIONS=3 \
OCTO_BROWSER_HEADLESS=false \
npx tsx src/run-journey.ts catalog-to-checkout
```

## Run on OKE (K8s Job)

```bash
JOURNEY=catalog-to-checkout \
RUN_ID=$(uuidgen) \
DNS_DOMAIN=octodemo.cloud \
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
IMAGE_TAG=latest \
ITERATIONS=5 \
envsubst < services/browser-runner/k8s/job.yaml | kubectl apply -f -

kubectl logs -f -n octo-browser -l run-id=$RUN_ID
```

Job exits on completion. Pod is retained for 24 h
(`ttlSecondsAfterFinished`) so you can inspect screenshots/HAR traces.

## Observability

Every page request carries:

```
X-Run-Id:       <uuid>
X-Operator:     browser-runner | <operator>
X-Workflow-Id:  browser.<journey-name>
User-Agent:     octo-browser-runner/1.0 (run_id=<uuid>; iter=<n>)
```

In OCI APM, filter:

```
http.request.header.x-run-id = '<uuid>'
```

In OCI RUM Sessions Explorer, filter User-Agent for
`octo-browser-runner/` — every iteration is one session.

HAR + screenshots are written to `/tmp/octo-browser-runner/` (or
`/artifacts` in the K8s Job). Load them into Playwright's trace viewer
(`npx playwright show-trace path/to/trace.zip`) for frame-by-frame
replay.

## Integration with octo-load-control

Phase 2 (`octo-load-control`) declares the `browser-journey` profile
with `ExecutorKind.BROWSER_RUNNER`. When that executor lands in
production (KG-027), it will render `k8s/job.yaml` on demand with the
run's UUID injected. For now, load-control returns
`{status: not-yet-implemented, phase: 4}` — we're in phase 4 right now;
the wire-up is the follow-up KG-027.

## Tests

```bash
npm test
# 6 tests — config loader invariants, no real browser launched
```

Full journey execution is validated by running the binary against
`drone.octodemo.cloud` with `OCTO_BROWSER_HEADLESS=false` and
eyeballing the Playwright browser window.

## Build + push

```bash
docker build --platform linux/amd64 \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-browser-runner:latest \
    services/browser-runner/
docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-browser-runner:latest
```

The image is ~1.5 GB because it bundles Chromium + OS deps. That's
Playwright's normal size; smaller is possible but not worth the ops
cost (custom base images rot, Microsoft's doesn't).
