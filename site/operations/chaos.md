# Chaos Engineering

Simulation controls for fault injection, gated behind IDCS SSO + internal service key.

## Controls

| Control | Endpoint | Range |
|---|---|---|
| Error rate | `POST /api/simulate/set` | 0.0 - 1.0 |
| DB latency (ms) | `POST /api/simulate/set` | 0 - 30000 |
| Slow responses | `POST /api/simulate/set` | 0 - 30000 ms |
| DB disconnect | `POST /api/simulate/set` | true/false |

## Usage

```bash
# Check current state
curl https://shop.example.com/api/simulate/status \
  -H "Authorization: Bearer <sso-token>"

# Inject 50% error rate
curl -X POST https://shop.example.com/api/simulate/set \
  -H "Authorization: Bearer <sso-token>" \
  -H "Content-Type: application/json" \
  -d '{"error_rate": 0.5}'

# Reset
curl -X POST https://shop.example.com/api/simulate/reset \
  -H "Authorization: Bearer <sso-token>"
```

## Authentication

Simulation endpoints require either:

1. **IDCS SSO token** — via `/api/auth/sso/login` flow
2. **Internal service key** — `X-Internal-Service-Key` header (CRM proxy)

Unauthenticated requests receive `401 Unauthorized`.

## CRM Cross-Control

The CRM Portal can trigger chaos on the Drone Shop via the simulation proxy, enabling cross-service failure scenarios visible in OCI APM distributed traces.
