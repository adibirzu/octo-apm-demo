# octo-cache

Shared Redis cache for the platform. **Observable by default** — every
call emits OTel span attributes (`cache.hit`, `cache.namespace`,
`cache.latency_ms`, etc.) so APM dashboards get hit/miss visibility
with zero additional metric plumbing.

## Why

Before this: every call to CRM for customer enrichment was a synchronous
HTTP hop (150 ms p95) and every catalog read was an ATP query. Both
patterns add unnecessary load on the upstream system and show up as
latency the customer notices.

After this: both patterns get a 5-minute TTL cache with a
permissive-fail contract — if Redis is unreachable, the app falls back
to the slow path without erroring.

## Components

| Path | Purpose |
|---|---|
| `k8s/statefulset.yaml` | Redis 7 StatefulSet in dedicated `octo-cache` namespace, LRU eviction, 512MB ceiling, appendonly persistence, 5GB PVC |
| `client/octo_cache/` | Async Python wrapper (`OctoCache` class) with OTel span enrichment |
| `client/pyproject.toml` | Package metadata — `pip install -e ".[dev]"` installs pytest + fakeredis + opentelemetry-sdk |
| `tests/test_octo_cache.py` | 6 tests using fakeredis: hit/miss classification, permissive fail, key-template cardinality, namespace separation |

## Span attributes the wrapper emits

| Attribute | Type | When |
|---|---|---|
| `cache.system` | string (`redis`) | always |
| `cache.namespace` | string (`shop:catalog`, `crm:customer`, …) | always |
| `cache.key` | string (template, never raw) | always |
| `cache.operation` | `get` \| `set` \| `delete` | always |
| `cache.hit` | bool | `get` only |
| `cache.latency_ms` | float | always |
| `cache.size_bytes` | int | `set` only |
| `cache.ttl_seconds` | int | `set` only |
| `cache.success` | bool | `set` only |

**Key template, not raw key.** `cache.key` carries `"by-email"` not
`"alice@example.invalid"` — otherwise every customer creates a unique
APM attribute value and the attribute-cardinality limit blows up.

## Usage — read-through pattern

```python
from octo_cache import OctoCache

cache = OctoCache(redis_url=os.getenv("OCTO_CACHE_URL", "redis://cache.octo-cache.svc.cluster.local:6379"))

async def get_catalog() -> list[dict]:
    cached = await cache.get("shop:catalog", "all")
    if cached is not None:
        return json.loads(cached)                # cache hit — fast path
    data = await load_from_atp()                 # slow path
    await cache.set("shop:catalog", "all", json.dumps(data), ttl_seconds=300)
    return data
```

Hits return in under 5 ms p95; misses match the DB path's latency.

## Permissive fail

If Redis is down, `get()` returns `None` (treated as a miss — app
falls back to DB), and `set()` returns `False` (cache update silently
skipped). The exception is recorded on the current OTel span so APM
shows the failure without customer impact.

## Deploy

### OKE

```bash
kubectl apply -f services/cache/k8s/statefulset.yaml
kubectl -n octo-cache rollout status statefulset/cache
```

Apps connect via `redis://cache.octo-cache.svc.cluster.local:6379`.

### Compose (VM)

Add to `deploy/vm/docker-compose-unified.yml`:

```yaml
  cache:
    image: redis:7.4-alpine
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "512mb", "--maxmemory-policy", "allkeys-lru"]
    restart: unless-stopped
    networks: [octo]
    volumes:
      - cache-data:/data

volumes:
  cache-data:
```

Then set `OCTO_CACHE_URL=redis://cache:6379` in the shop + crm
services.

## Wiring into shop + crm

Two concrete wire-ups land in follow-up commits (tracked as
KG-025 and KG-026 respectively):

- **KG-025**: shop catalog read-through (`/api/products`) — 5m TTL,
  invalidate on admin edit.
- **KG-026**: CRM customer enrichment — 5m TTL on
  `/api/integrations/crm/customer-enrichment`.

## Tests

```bash
cd services/cache/client
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd ..
python -m pytest -q
# 6 passed
```

Tests use `fakeredis` so no live Redis is required. Coverage:

- miss → set → hit round-trip + span shape
- connection error on `get` → returns `None`, records exception on span
- connection error on `set` → returns `False`, records exception
- `delete` is best-effort (swallows errors)
- `cache.key` attribute is the template, not the raw key
- namespace separation works (same `key` in two namespaces → independent)

## Observability via APM

In Trace Explorer, filter:

```
attributes.cache.system = 'redis'
```

Split the latency histogram by `cache.hit` — left bar is misses, right
bar is hits. The hit ratio is `count(cache.hit=true) / count(cache.*)`.

To find a specific namespace:

```
attributes.cache.system = 'redis' and attributes.cache.namespace = 'crm:customer'
```

## Next

Phase 6 unblocks:
- Profile `cache-miss-storm` in `octo-load-control` (already declared).
- Workshop Lab 11 (once Phase 8 is done) — cache cold-start drill.

Future work (KG-025, KG-026) wires the cache into the existing
shop + CRM code paths.
