# Auto-remediation flow

```
alarm ─► incident ingest ─► correlation rule ─► playbook
                                                    │
                                                    ▼
                             drilldown_pivot (parallel MCP tools)
                                                    │
                                                    ▼
                              RootCauseHypothesis + evidence
                                                    │
                     ┌──────────────────────────────┴─────────────┐
                     ▼                                            ▼
        tier "low"                                       tier ≥ "medium"
        auto-execute  (AUTOREMEDIATE_ENABLED)          wait for approval
                     │                                            │
                     ▼                                            ▼
          verify via la_workflow_health                   execute then verify
```

## Playbooks shipped

| id | tier | action |
| --- | --- | --- |
| `db-slow-remediation` | medium | evidence → slow-SQL advisor → propose index |
| `crm-sync-failure` | medium | circuit-break → restart → verify |
| `pool-exhaustion` | high | propose pool bump + rolling restart |
| `chaos-cleanup` | low | clear stuck scenarios (auto) |
| `waf-tighten-suggest` | low | correlate → propose rule tightening |

## Non-negotiables

- Tools are read-only; any write surface is a **proposal**.
- Shop mutations go through the Helm/Terraform pipeline, never a live
  admin endpoint. This preserves the Shop's minimal attack surface.
- `AUTOREMEDIATE_ENABLED=false` by default.
