# Lab 06 — WAF event investigation

## Objective

Investigate a WAF event from end to end: what triggered it, was it
malicious, what did the user actually try to do.

## Time budget

30 minutes.

## Prerequisites

- Lab 01.
- WAF policy `octo-waf-shop` attached to the shop's load balancer
  (created by `deploy/terraform/modules/waf/`).
- WAF mode: `DETECTION` (default — see
  [WAF observability](../observability-v2/waf-observability.md)).

## Steps

### 1. Trigger a WAF rule

Send a request that looks like SQL injection. WAF will detect
(`DETECTION` mode) without blocking.

```bash
curl -sS "https://shop.example.tld/api/products?id=1' OR '1'='1" \
    -H "User-Agent: workshop-lab-06"
```

You'll get a normal response (because we're in DETECTION mode), but
WAF logs the trigger.

### 2. Find the event in OCI Logging

Console → Logging → **Search Logs**.

Pick the WAF log group (`octo-waf-logs` typically), then run:

```
search "search 'data.requestUserAgent' = 'workshop-lab-06'"
```

Within ~30 s you'll see the WAF entry. Open it.

### 3. Read the WAF record

Key fields:

- `data.action` — `DETECTED` (vs `BLOCKED` in BLOCK mode).
- `data.matchedRules[].ruleType` — typically
  `SQLI_INJECTION_DETECTION`.
- `data.matchedRules[].message` — human-readable rule name.
- `data.requestUri` — the URL that triggered.
- `data.clientIpAddress` — the source IP.
- `data.requestHeaders` — full headers (useful to identify scanners).

### 4. Pivot to the application trace

The WAF log carries `data.requestId`. The shop logs the same value
under `request_id`. Join them:

```
'Log Source' = 'octo-shop-app-json'
  | where request_id = '<WAF_REQUEST_ID>'
  | head limit = 5
```

If the request reached the app (it should, in DETECTION mode), this
returns the matching app log record. From there, you have an
`oracleApmTraceId` → APM Trace Explorer drill-down.

### 5. Decide

Compare:

- **WAF**: SQL-injection rule fired.
- **App log**: route handler ran successfully (sanitized via
  parameterized query).
- **APM trace**: SQL span shows the parameter was bound, not interpolated.

Verdict: WAF caught a probe, the app correctly resisted it. **Not an
incident** — this is the system working as designed in DETECTION mode.

If you saw all three signals lined up but the app log showed a SQL
**parsing error**, that would be a real concern: the shop didn't
sanitize the input. (None of our routes are vulnerable, so you won't
see this — but the muscle memory of the comparison is the lesson.)

### 6. Promote to BLOCK if appropriate

For repeat offenders, the WAF policy can be flipped to BLOCK:

```bash
oci waf web-app-firewall update \
    --web-app-firewall-id "$WAF_POLICY_SHOP_OCID" \
    --waf-config '{ "actions": [...override...] }'
```

We don't actually flip it during the workshop — just know where the
lever is.

## Verify

```bash
./tools/workshop/verify-06.sh
```

Expected:

```
✓ WAF log group reachable
✓ at least one DETECTED action in last 1h
✓ WAF event correlatable to app log via request_id
PASS — Lab 06 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| WAF event not in Logging | WAF policy not attached to LB | `oci.oraclecloud.com/waf-policy-ocid` annotation on the LoadBalancer Service must point at the WAF policy OCID |
| `request_id` join returns no app rows | App middleware not honoring `X-Request-Id` from LB | The shop's middleware must read incoming `X-Request-Id` and stamp it on every log; check `shop/server/main.py` request middleware |

## Read more

- [Observability v2 → WAF observability](../observability-v2/waf-observability.md)
- [Architecture → Correlation Contract](../architecture/correlation-contract.md)

---

[← Lab 05](lab-05-metric-and-alarm.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 07 → Saved searches →](lab-07-saved-search.md)
