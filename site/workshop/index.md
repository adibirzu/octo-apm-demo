# OCI Observability Onboarding Workshop

A hands-on workshop that teaches how to operate the OCI observability
stack using `octo-apm-demo` as the playground. Ten labs, ~6 hours total
if done in one sitting; designed to be split across two half-days.

!!! abstract "Who this is for"
    Engineers, SREs, and platform operators who:

    - know their way around a terminal and a browser console,
    - have access to an OCI tenancy with `octo-apm-demo` deployed,
    - want to learn the OCI APM + RUM + Logging + Log Analytics +
      Stack Monitoring + Monitoring + Cloud Guard chain end-to-end.

## What you'll be able to do at the end

- Find any HTTP request's full distributed trace across browser, edge,
  shop, and CRM in under 30 seconds.
- Pivot from a Log Analytics record to its APM trace and back.
- Build a Log Analytics saved search and pin it to a dashboard widget.
- Author an OCI Monitoring alarm with a useful annotation contract.
- Drill from an ATP wait event to the source SQL to the trace that
  emitted it.
- Investigate a WAF event and decide if it was a real attack or a noisy
  scanner.
- Run a chaos drill, observe what breaks, and resolve it without losing
  your audit trail.
- Diagnose a failed checkout from a customer report ("it didn't work")
  to a one-line fix.

## Format

Each lab follows the same shape:

| Section | What it does |
|---|---|
| **Objective** | One sentence: what you'll learn. |
| **Time budget** | Honest estimate. |
| **Prerequisites** | Specific OCI policies, env access, prior labs. |
| **Steps** | OCI Console + CLI parallel — pick the one you prefer. |
| **Verify** | A `tools/workshop/verify-NN.sh` script you run; pass = lab complete. |
| **Troubleshooting** | The 3 most common things that go sideways. |
| **Read more** | Underlying docs, OCI service references. |

## The 10 labs

| # | Lab | Time | Pre-reqs |
|---|---|---|---|
| 01 | [Your first trace](lab-01-first-trace.md) | 20 min | platform deployed |
| 02 | [Trace ↔ Log correlation](lab-02-trace-log-correlation.md) | 30 min | lab 01 |
| 03 | [Find a slow SQL from an APM span](lab-03-slow-sql-drill-down.md) | 30 min | lab 02 |
| 04 | [Detecting a frontend outage from RUM](lab-04-rum-outage-detection.md) | 25 min | lab 01 |
| 05 | [Custom metric + alarm](lab-05-metric-and-alarm.md) | 40 min | lab 01 |
| 06 | [WAF event investigation](lab-06-waf-event-investigation.md) | 30 min | lab 01 |
| 07 | [Build a Log Analytics saved search](lab-07-saved-search.md) | 35 min | lab 02 |
| 08 | [Stack Monitoring + ATP health](lab-08-stack-monitoring-atp.md) | 40 min | lab 03 |
| 09 | [Chaos drill](lab-09-chaos-drill.md) | 50 min | labs 01-05 |
| 10 | [End-to-end debug a failed checkout](lab-10-failed-checkout.md) | 60 min | all prior labs |

Total: ~6 h. Recommended split: labs 1-5 day one (~2.5h),
labs 6-10 day two (~3.5h).

## Prerequisites checklist

Before lab 01:

- [ ] Octo APM Demo deployed in your tenancy. Either path is fine:
    - Unified VM ([new-tenancy guide](../getting-started/new-tenancy.md))
    - OKE ([oke-deployment guide](../getting-started/oke-deployment.md))
- [ ] Your laptop has: `oci` CLI 3.40+, `kubectl`, `jq`, `curl`, a
      modern browser.
- [ ] You have `Read` policy on APM domains, log groups, Log Analytics
      namespace, Monitoring metrics, Stack Monitoring resources, WAF
      policies in the demo's compartment.
- [ ] Optional but recommended: `octo-traffic-generator` running so APM
      and RUM have signal. ([deploy guide](https://github.com/adibirzu/octo-apm-demo/tree/main/tools/traffic-generator))
- [ ] Verified the platform is reachable:
    ```bash
    curl -s https://drone.octodemo.cloud/ready   | jq
    curl -s https://backend.octodemo.cloud/ready | jq
    ```
    Both should return `database.reachable=true`.

## Workshop conventions

- Every shell snippet assumes `bash` (not zsh-specific syntax). On
  macOS, `bash` from Homebrew works the same.
- Every URL uses `octodemo.cloud`. If your tenancy uses a different
  `DNS_DOMAIN`, mentally substitute.
- "OCI Console" instructions assume the [Frankfurt region UI](https://cloud.oracle.com/?region=eu-frankfurt-1).
  If you use another region, the menu paths are identical; only the
  region selector differs.
- Code blocks marked with `# verify` are the snippets the
  `tools/workshop/verify-*.sh` scripts execute on your behalf.

## Certification

After lab 10, run:

```bash
./tools/workshop/certify.sh
```

It re-runs every per-lab verifier in sequence and prints a passport
showing which labs you completed. Save the output — it's evidence you
can attach to internal training records or PR descriptions.

## License

Same MIT license as the rest of the repo. Fork, adapt, ship for your
own tenancy. PRs welcome — especially new labs covering OCI services we
haven't reached yet (API Gateway, Functions, Streaming, etc.).
