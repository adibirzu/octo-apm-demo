# Architecture diagrams (drawio)

Three diagrams describing the platform from different angles. Open any
of them at [app.diagrams.net](https://app.diagrams.net) → *File* →
*Open from → Device* and select the `.drawio` file.

| File | Focus |
|---|---|
| [`platform-overview.drawio`](./platform-overview.drawio) | Full topology — users → WAF → OKE → data + observability plane, every service + every OCI backend |
| [`observability-flow.drawio`](./observability-flow.drawio) | MELTS signal flow — how traces / logs / metrics / events / SQL-perf reach OCI APM / Logging / Log Analytics / Stack Monitoring / Events |
| [`deploy-topology.drawio`](./deploy-topology.drawio) | Build path + OCIR + three deploy targets (OKE, single-VM, local-stack) with per-target trade-offs |

## Re-rendering

The diagrams are authored in [draw.io](https://www.drawio.com/) (now
`diagrams.net`). They work offline and in VS Code with the
[Draw.io Integration extension](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio).

To re-export to SVG/PNG for embedding in mkdocs:

```bash
# Install the drawio CLI once
npm install -g @hediet/drawio-cli

# Export to SVG
drawio --export --format svg --output platform-overview.svg platform-overview.drawio

# Export to PNG at 2x DPI
drawio --export --format png --scale 2 --output platform-overview.png platform-overview.drawio
```

Commit both the `.drawio` source and the rendered asset — reviewers
on the PR can then diff the image directly.

## Conventions

- **Yellow fill** (`#FEF3C7` / `#D97706` border) — application pods (FastAPI, Go, Playwright).
- **Green fill** (`#D1FAE5` / `#059669` border) — OCI observability services.
- **Blue fill** (`#DBEAFE` / `#2563EB` border) — OCI platform services (Vault, IDCS, OCIR, API Gateway).
- **Red fill** (`#FEE2E2` / `#DC2626` border) — WAF + remediator (security-critical paths).
- **Purple fill** (`#F3E8FF` / `#9333EA` border) — data plane infrastructure (Redis, Object Storage).
- **Orange fill** (`#FB923C` / `#9A3412` border) — storage (ATP, Object Storage).

Arrows with **solid** strokes = synchronous request path. **Dashed**
strokes = asynchronous, event-driven, or configuration flow.

## Authoring gotchas

drawio silently rejects a whole diagram if any `mxCell value="…"`
attribute contains constructs its parser does not handle. Avoid:

- HTML-escaped angle brackets inside text (`&lt;region&gt;`) — use
  literal placeholders like `REGION.ocir.io/NAMESPACE/` instead.
- Unicode bullets (`•`) — use hyphens or numbered lists.
- Un-escaped quotation marks in node labels — use `&quot;` or drop.
- Hex line-break entities (`&#xa;`) — prefer decimal `&#10;`. Both
  are LF but decimal parses more reliably across drawio versions.

When in doubt, validate XML locally:

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('file.drawio'); print('OK')"
```

…and run the duplicate-id + dangling-edge check:

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET
tree = ET.parse('file.drawio')
ids = [c.get('id') for c in tree.iter('mxCell')]
dups = [i for i in set(ids) if ids.count(i) > 1]
print(f'cells={len(ids)} unique={len(set(ids))} dups={dups}')
for c in tree.iter('mxCell'):
    if c.get('edge') == '1':
        for endpoint in ('source', 'target'):
            ref = c.get(endpoint)
            if ref and tree.find(f'.//mxCell[@id="{ref}"]') is None:
                print(f'{c.get("id")}: dangling {endpoint}={ref}')
PY
```

Past failure: `deploy-topology.drawio` with `&lt;region&gt;` escapes +
bullet characters silently refused to open. Rewriting values with
plain ASCII + `&#10;` line breaks fixed it.
