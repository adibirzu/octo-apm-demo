# Stress Demo — LB Header-Routing Runbook

Operator runbook for the Phase 7 OCI Flexible Load Balancer routing
policy that pins requests carrying the `X-Octo-Stress-Target: oke`
header to the OKE backend set, leaving the VM backend set untouched.

This rule preserves the DEPLOY-03 round-robin contract between VM
and OKE backends (Phase 4 deployment-parity contract) during the
stress demo: only requests explicitly tagged by the in-cluster
`octo-stress-runner` reach OKE; all production VM traffic keeps its
existing round-robin path (D-09).

## When to apply

Apply this rule **in the same operator window** that enables the
Cluster Autoscaler add-on — both ship together as the "Phase 7
operator window" (see
[`deploy/oke/configure-cluster-autoscaler.sh`](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/oke/configure-cluster-autoscaler.sh)).
Without it the stress run still functions, but stress traffic will
land on the VM round-robin half of the LB and dilute the
demo signal.

## Prerequisites

| Item | How to set | Notes |
|---|---|---|
| `OCTO_LB_OCID` | `export OCTO_LB_OCID="<ocid-of-octo-LB>"` | Placeholder — never commit a live OCID. Source from your tenancy's terraform output `lb_id`. |
| OCI CLI profile | `export OCI_CLI_PROFILE="<profile>"` | Must have `manage load-balancers` on the LB compartment. |
| Operator approval | Out-of-band PR review | The runbook performs a mutating `oci lb routing-policy update`. Live apply is **not** automated — operator runs it from a controlled host. |
| Existing OKE backend-set name | `oci lb backend-set list --load-balancer-id "${OCTO_LB_OCID}"` | The expected name is `oke-backend-set`; adjust the rule body if your tenancy differs. |

## Steps

### 1. Inspect the current routing policy

```bash
oci lb routing-policy list \
    --load-balancer-id "${OCTO_LB_OCID}" \
    --profile "${OCI_CLI_PROFILE}"
```

Expected: an existing routing policy named `octo-default-policy` that
round-robins between `vm-backend-set` and `oke-backend-set`. **Do not
delete it** — we are appending one higher-priority rule, not
replacing the policy.

### 2. Compose the header-pin rule

The rule expression matches requests carrying the
`X-Octo-Stress-Target: oke` header (the in-cluster
`octo-stress-runner` always sets it; see `tools/stress-runner/`
plan 07-03) and pins them to `oke-backend-set`:

```bash
cat > /tmp/octo-stress-pin-rule.json <<'EOF'
[
  {
    "name": "octo-stress-pin-oke",
    "condition": "http.request.headers[(i 'X-Octo-Stress-Target')] eq (i 'oke')",
    "actions": [
      {
        "name": "FORWARD_TO_BACKENDSET",
        "backendSetName": "oke-backend-set"
      }
    ]
  }
]
EOF
```

Notes on the expression:

- `(i 'X-Octo-Stress-Target')` makes the header-name comparison
  case-insensitive (OCI LB routing-rule grammar).
- The rule is **additive** — it precedes the round-robin default,
  so VM-bound traffic without the header keeps its existing path.

### 3. Apply the rule (gated)

```bash
# Dry-run preview — does NOT mutate state
oci lb routing-policy update \
    --load-balancer-id "${OCTO_LB_OCID}" \
    --routing-policy-name "octo-default-policy" \
    --rules "$(cat /tmp/octo-stress-pin-rule.json)" \
    --force \
    --dry-run \
    --profile "${OCI_CLI_PROFILE}"
```

If the dry-run output matches the rule above, request operator
confirmation in your change-management channel, then drop `--dry-run`
to apply.

### 4. Verify the rule is live

```bash
# Send a stress-tagged request — must hit OKE
curl -H "X-Octo-Stress-Target: oke" \
    "https://shop.${DNS_DOMAIN}/api/products" -v

# Same path without the header — should round-robin (VM or OKE)
curl "https://shop.${DNS_DOMAIN}/api/products" -v
```

Inspect the `Server` response hint (or any OKE-only header your
ingress adds, e.g. `X-Served-By: oke-ingress-nginx`) to confirm the
tagged request reaches the OKE backend set.

## Rollback

```bash
# Option A — disable the rule by removing it from the policy
oci lb routing-policy update \
    --load-balancer-id "${OCTO_LB_OCID}" \
    --routing-policy-name "octo-default-policy" \
    --rules '[]' \
    --force \
    --profile "${OCI_CLI_PROFILE}"

# Option B — drop the routing policy attachment from the listener
# (last-resort, restores raw round-robin)
oci lb listener update \
    --load-balancer-id "${OCTO_LB_OCID}" \
    --listener-name "octo-https-listener" \
    --routing-policy-name "" \
    --force \
    --profile "${OCI_CLI_PROFILE}"
```

Option A is the standard rollback; Option B is for incident response
if the rule is the suspected cause of a broader outage.

## Audit + recording

When applying the rule live during a workshop:

1. Record the workshop `run_id` in the change-management PR comment
   (Phase 7 audit contract — same shape as the chaos audit trail).
2. The OCI LB CLI mutation lands in the tenancy's OCI Audit log
   automatically (T-07-46 mitigation).
3. After the workshop, attach the audit-log query to the post-run
   doc:

   ```bash
   oci log-analytics query \
       --namespace-name "$LA_NAMESPACE" \
       --query-string "'Log Source' = 'OCI Audit Logs' and lb_id = '${OCTO_LB_OCID}' and (event_name like 'UpdateRoutingPolicy%')"
   ```

## Cross-references

- **[Workshop Lab 11 — OKE autoscaling](../workshop/lab-11-oke-autoscaling.md)**
  — the lab that exercises this rule.
- **`deploy/oke/configure-cluster-autoscaler.sh`** — the Cluster
  Autoscaler operator script; this LB rule and the CA add-on apply
  in the same operator window (Phase 7 deferred operator-window
  items).
- **DEPLOY-03 contract** — the VM/OKE round-robin constraint that
  makes header-based pinning necessary (Phase 4 deployment-parity
  CONTEXT).
- **Operator runbook neighbour**: [Chaos engineering](chaos.md) —
  a similarly audited, operator-gated mutation pattern.

---

!!! warning "No live OCIDs / IPs in this runbook"
    All identifiers above are `${OCTO_LB_OCID}` / `${DNS_DOMAIN}` /
    `${OCI_CLI_PROFILE}` placeholders. Per the global "no PII /
    secrets / public IPs" rule, never substitute live values into a
    committed copy of this file.
