---
title: Code Knowledge Map
description: A queryable knowledge map of the codebase — services, modules, routes, tests, and design rationale linked into a single graph
---

# Code Knowledge Map

The OCTO APM Demo platform spans roughly ten cooperating services written in
Python, Java, and Go, glued together with Helm charts, Terraform modules, OCI
Functions, and a sizable mkdocs site. Understanding how a feature touches all of
those layers by reading directories is slow — and most onboarding questions
("what runs when a customer pays?", "where are the payment tests?", "which docs
describe the auto-remediator?") cross at least three of them.

The **code knowledge map** is a JSON graph of the entire repository. Every
Python class and function, every Java method, every FastAPI route, every Helm
template, every mkdocs page, and every extracted `# rationale:` comment becomes
a node. Edges connect them through call-graph relationships, imports, test
coverage, and documentation references. The result is a single file (and an
accompanying HTML viewer) you can query to answer cross-cutting questions about
the codebase without grepping ten directories by hand.

This page documents what's in the map, how it's built, how to query it, and how
it complements runtime observability (OCI APM, Logging, Log Analytics).

> Cross-reference: see [Platform Overview](../architecture/platform-overview.md)
> and [Service Inventory](../architecture/service-inventory.md) for the runtime
> topology the map indexes.

## Why it's useful

A few concrete scenarios that the map handles well:

- **Tracing a feature footprint.** A query like "show me every node related to
  payment" returns roughly 905 nodes spanning `shop/server`,
  `services/apm-java-demo`, `shop/tests`, and several pages under `site/`.
  Reading those nodes (and the edges between them) gives you the full
  cross-language surface area of a single feature in seconds.
- **Finding test coverage gaps.** Modules that have no inbound edge from any
  `tests/` node are visible by exclusion. Useful before a release: any
  payment-adjacent code without a test edge is a candidate for a new test.
- **Surfacing design rationale.** The AST step extracts comments of the form
  `# rationale: ...` (and Java/Go equivalents). Pulling every rationale node
  near a given module is a fast way to remember *why* a non-obvious choice was
  made.
- **Detecting doc-vs-code drift.** Routes declared in
  `crm/server/modules/**` or `shop/server/routes/**` can be compared against
  routes mentioned in `site/**`. When a route exists in code but no doc node
  references it (or vice versa), the drift is visible as a missing edge.
- **Onboarding.** A new contributor can ask "what touches login?" and get a
  one-page answer instead of a multi-hour codebase tour.

## What's in the graph

**Node types**

| Type | What it represents | Where it comes from |
|------|--------------------|---------------------|
| `code` | A function, class, method, or file | AST extraction over `.py`, `.java`, `.go`, `.ts` sources |
| `document` | A markdown section in `site/` | Headings in mkdocs source files |
| `rationale` | A `# rationale:` (or equivalent) comment block | Pattern-matched during AST extraction |
| `config` | A Helm template, Terraform module, or YAML manifest | Structural parse of `deploy/**` |

**Edge types**

| Type | Meaning |
|------|---------|
| `calls` | Function A invokes function B |
| `imports` | Module A imports module B |
| `references` | Doc section references a code identifier by name |
| `tests` | A test file exercises a code symbol |
| `documents` | A doc section documents a route, class, or module |

**Communities**

Nodes are clustered into communities using a Louvain-style algorithm. A
"community" is a tightly connected subgraph — typically a feature area. On the
current repo, the payment community contains roughly 91 nodes; the
auto-remediator community contains around 60. Community membership is a useful
filter when scanning the report.

**Scale on this repo** (approximate, as of the most recent build):

- ~6,700 nodes
- ~8,800 edges
- ~590 communities

These numbers grow gradually as services and docs are added. The build is
incremental, so growth doesn't translate linearly into build time.

## How to build it

The map is produced by an open-source AST-extraction tool. Install it once,
then run the build from the repository root.

```bash
# One-time install of the AST extractor (uses npm as the distribution channel)
npm install -g graphify

# Build the map — incremental, uses an on-disk AST cache
graphify update .
```

Output is written to a local build directory that is gitignored. Typical first
build is 60–90 seconds; subsequent incremental builds complete in 15–30
seconds because the AST cache shortcuts unchanged files.

Three artifacts are produced:

| File | Purpose |
|------|---------|
| `graph.json` | The full graph — nodes, edges, community labels, metadata |
| `graph.html` | An interactive viewer (zoom, pan, search, community highlight) |
| `GRAPH_REPORT.md` | A human-readable summary grouped by community |

## How to query it

The right interface depends on the question.

**Skim the summary report.** Open `GRAPH_REPORT.md` for a tour of the
communities. Each community section lists its top nodes by degree (number of
connecting edges) and a one-line description. This is the fastest way to get
oriented if you've never looked at the map before.

**Use the interactive viewer.** Open `graph.html` in any modern browser. It
supports zoom, pan, full-text search across node labels, and community
highlighting. The viewer is usable up to roughly 10,000 nodes; beyond that,
browser layout becomes the bottleneck (see [Limitations](#limitations)).

**Query the JSON directly.** For anything programmatic, `jq` is the simplest
tool. The examples below are real queries you can run against `graph.json`.

### Example queries

Find every node whose label mentions payment:

```bash
jq '.nodes[] | select(.label | test("payment"; "i")) | .label' graph.json | head
```

Pull rationale comments anywhere near the orders module:

```bash
jq '.nodes[]
    | select(.file_type=="rationale" and (.source_file | test("orders")))' \
    graph.json
```

Count nodes per community (top 10 communities by size):

```bash
jq -r '.nodes[] | .community' graph.json | sort | uniq -c | sort -rn | head
```

List FastAPI routes that no doc node references (drift detection):

```bash
jq '[.nodes[] | select(.kind=="route")] as $routes
    | [.edges[] | select(.type=="documents") | .target] as $documented
    | $routes | map(select(.id as $id | $documented | index($id) | not))
    | .[].label' graph.json
```

Find modules with no inbound `tests` edge (coverage gap candidates):

```bash
jq '[.edges[] | select(.type=="tests") | .target] as $tested
    | .nodes[]
    | select(.kind=="module" and (.id as $id | $tested | index($id) | not))
    | .label' graph.json
```

For richer queries — multi-hop neighborhoods, shortest paths between two
features — load `graph.json` into a dedicated graph tool such as Cytoscape or
Gephi. The JSON shape is generic enough that no conversion script is needed.

## Integration with observability

The map is a **development-time artifact**, separate from the runtime
telemetry that OCI APM, Logging, and Log Analytics emit. The two complement
each other:

- Use the **map** to find code, tests, docs, and design rationale.
- Use **OCI APM** to find what that code actually did in production: which
  spans were slow, which dependencies were called, which traces failed.

A representative bridging workflow:

1. APM Trace Explorer flags a slow `checkout` span on the Drone Shop.
2. The span name (e.g., `POST /api/checkout`) identifies the FastAPI route.
3. Query the map for every node connected to that route — handler function,
   helper modules, payment-sidecar call, tests, and docs.
4. From there, you have the full development context to investigate why the
   span was slow: the candidate code paths, the relevant rationale comments,
   and the tests that should have caught the regression.

This pattern shows up frequently in incident reviews and is the main reason
the map exists.

## Limitations

- **Viewer scale.** The interactive HTML view starts to lag above ~10,000
  nodes because browser layout becomes the bottleneck. Raise
  `GRAPHIFY_VIZ_NODE_LIMIT` to extend it, or pass `--no-viz` to the build
  command and consume `graph.json` in a desktop tool instead.
- **Language coverage.** The AST extractor is language-aware for Python,
  Java, TypeScript, JSON, YAML, and Markdown. Exotic file types (Dockerfile
  recipes, raw shell scripts, HCL beyond the standard structures) are
  modeled as opaque file nodes — useful for context but with no internal
  detail.
- **Cross-language edges are best-effort.** A Python service calling a Java
  service over HTTP is inferred from string patterns (route paths, client
  identifiers), not from a true call graph. For production behavior across
  language boundaries, **runtime call graphs from APM are more reliable**.
  Treat cross-language map edges as hints, not ground truth.
- **No semantic understanding of comments.** Rationale extraction is
  pattern-based. A comment that explains a design choice without using a
  recognized marker (`# rationale:`, `// rationale:`, etc.) is not captured.

## Refresh policy

The map is rebuilt on demand, not on every commit. Suggested triggers:

- A new service is added or removed from `services/` or `crm/` or `shop/`.
- A significant refactor moves modules between directories.
- A new mkdocs section is added under `site/`.
- A release is being prepared and a coverage-gap or drift scan is useful.

CI does **not** run the build. The output artifacts (especially `graph.html`
and `graph.json`) are large and would bloat the git history; they are produced
locally and consumed locally.

## Glossary

- **Community** — A cluster of nodes detected by graph community detection
  (a Louvain-style algorithm). Roughly corresponds to a feature area in the
  codebase.
- **Edge** — A typed relationship between two nodes: `calls`, `imports`,
  `tests`, `references`, or `documents`.
- **Rationale node** — A code comment that explains *why* a design choice
  was made, extracted by the AST step from comments matching a small set
  of recognized markers (e.g., `# rationale:`).
- **Degree** — The number of edges connected to a node. High-degree nodes
  are typically central abstractions (a `Settings` class, an HTTP client,
  a shared logger) and are good starting points when exploring a community.

## See also

- [Platform Overview](../architecture/platform-overview.md) — runtime
  topology the map indexes.
- [Service Inventory](../architecture/service-inventory.md) — per-service
  surface area.
- [APM Drilldown](apm-drilldown.md) — the runtime counterpart to the map
  for production behavior.
