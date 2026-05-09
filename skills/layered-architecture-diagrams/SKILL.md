---
name: layered-architecture-diagrams
description: Use when creating or updating editable architecture diagrams, especially draw.io or SVG diagrams that need layers, flow animation, observability paths, or maintainable platform topology documentation.
---

# Layered Architecture Diagrams

Use this workflow for platform, deployment, observability, and data-flow
architecture diagrams.

## Source Of Truth

- Keep an editable `.drawio` file as the source of truth.
- If the docs embed an SVG, commit the SVG beside the `.drawio` source.
- Do not commit private IPs, OCIDs, tenancy names, operator allowlists, or
  real secrets. Use placeholders or public hostnames approved for docs.

## Layer Model

Create draw.io layers as top-level `mxCell` entries under `parent="0"`:

1. `00 Background` - title, sections, legends, boundaries.
2. `10 Edge And Identity` - browser, DNS, WAF, LB, API Gateway, IAM.
3. `20 Applications` - shop, admin/CRM, workflow gateway, workers, sidecars.
4. `30 Data And AI` - ATP, Redis, Object Storage, Select AI, GenAI.
5. `40 Observability` - OTel, OCI APM, RUM, Logging, LA, Stack Monitoring.
6. `50 Flow Overlay` - request arrows, telemetry arrows, async fan-out.
7. `60 Notes` - edit hints, sanitization policy, version note.

Put every node or edge in the most specific layer. Avoid a flat
`parent="1"` diagram for anything expected to be edited later.

## Flow Movement

- In `.drawio`, keep flow edges on the `50 Flow Overlay` layer and label each
  path with the workflow name, for example `login traceparent` or
  `order -> CRM sync`.
- In SVG previews, add animated dashed overlays for the same flow edges:
  `stroke-dasharray`, `stroke-dashoffset`, and a short linear CSS animation.
- Include a `prefers-reduced-motion: reduce` rule that disables animation.
- Use solid arrows for synchronous request paths, dashed arrows for telemetry
  and async/event paths, and dotted arrows for optional integrations.

## Maintainability Rules

- Use stable, readable IDs: `shop-app`, `oracle-atp`, `flow-login-apm`.
- Keep labels short; move details into notes or the surrounding markdown.
- Use ASCII in `.drawio` labels unless the file already uses non-ASCII.
- Keep color semantics consistent:
  - Blue: edge/platform services
  - Yellow: application services
  - Orange: database/storage
  - Green: observability services
  - Purple: AI/workflow services
  - Red: security/remediation controls
- Add a small legend in the background or notes layer.

## Validation

Before finishing:

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('site/architecture/diagrams/private-demo-observability-reference.drawio'); print('drawio ok')"
python3 -c "import xml.etree.ElementTree as ET; ET.parse('site/architecture/diagrams/private-demo-observability-reference.svg'); print('svg ok')"
rg -n 'example[-]org|github[.]com/example|203\\.0\\.113|ocid1\\.' site/architecture/diagrams
```

If the diagram is published through MkDocs, run `python -m mkdocs build
--clean --strict` and inspect the generated page for stale links.
