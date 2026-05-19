# Planning / Repo Security Rules

This file is for repo contributors. The intent is to keep internal tenancy topology out of public git history.

## What NEVER goes into a committed file

| Category | Examples | Use this placeholder instead |
|---|---|---|
| Tenancy OCIDs | `ocid1.tenancy.oc1..aaaaaaaa…` | `<EMDEMO_TENANCY_OCID>`, `<CAP_TENANCY_OCID>`, etc. |
| Compartment OCIDs | `ocid1.compartment.oc1..aaaaaaaa…` | `<LOGANALYTICS_COMPARTMENT_OCID>` |
| Instance / cluster / NSG / LB / subnet / VNIC / boot-volume OCIDs | any `ocid1.<resource>.oc1.<region>.<id>` | `<JUMPHOST_INSTANCE_OCID>`, `<OKE_CLUSTER_OCID>`, etc. |
| Log Analytics / APM identifiers | `ocid1.loganalytics*`, APM domain IDs like `aaaadhp5ewo…` | `<LA_CLUSTER_ENTITY_OCID>`, `<APM_DOMAIN_ID>` |
| Tenancy registry namespace | `fr4zqfimuxtr`, `axoxdievda5j`, `id9y6mi8tcky` | `${OCIR_TENANCY}` |
| Log Analytics namespace | `axfo51x8x2ap` | `<LA_NAMESPACE>` |
| Auth tokens, datakeys, install keys | base64 strings, hex strings 32+ chars | `<APM_PRIVATE_DATAKEY>`, `<INTERNAL_SERVICE_KEY>` — never inline |
| Public IPs of internal infra | `161.153.x.x`, `144.24.x.x`, `130.61.x.x`, `129.153.x.x` (LBs, jumphost, control-plane, OKE API) | `<EMDEMO_LB_PUBLIC_IP>`, `<JUMPHOST_PUBLIC_IP>`, etc. |
| Private IPs revealing topology | `10.42.x.x` worker / VM subnets | `<OKE_WORKER_PRIV_IP>`, `<VM_SHOP_PRIV_IP>`, etc. |
| Allowed-source IPs in NSG rules | developer egress `/32`s | `<DEV_EGRESS_IP_*>` |

Real OCIDs and IPs belong in:
- `credentials/emdemo/outputs.json` and similar files (already gitignored via `credentials/`, `outputs.json`, `**/outputs.json`)
- Local environment variables (`.env.local`, also gitignored)
- OCI Vault / Kubernetes Secrets (resolved at runtime, never in source)

## Why placeholders even for non-secret OCIDs

OCIDs aren't credentials, but they:
1. Reveal which tenancy you're in (`oc1..aaaaaaaa5s2vdjjryd…` is a fingerprint of `emdemo`).
2. Expose internal architecture topology (instance counts, NSG layout, LB topology).
3. Enable correlation with other leaked sources (CVE write-ups, support tickets, screenshots).
4. Violate the project-wide rule encoded in `~/.claude/CLAUDE.md` "Security: No PII, Secrets, or Public IPs in Any Project".

When in doubt, redact. The placeholder format is `<UPPERCASE_TOKEN_WITH_UNDERSCORES>` so it's easy to grep for unfilled tokens before any deploy.

## Pre-commit audit

Before every commit, run:
```bash
git diff --cached -U0 | grep -nE 'ocid1\.(tenancy|compartment|instance|cluster|networksecuritygroup|loadbalancer|subnet|vnic|bootvolume|loganalytics[a-z]+|user)\.oc1\.[a-z]*\.[a-z0-9]+' && echo "ABORT: real OCID in staged diff" && exit 1
git diff --cached -U0 | grep -nE '\b(130\.61|161\.153|144\.24|129\.153|141\.147|82\.77|109\.166)\.[0-9]+\.[0-9]+\b' && echo "ABORT: real public IP in staged diff" && exit 1
git diff --cached -U0 | grep -nE 'fr4zqfimuxtr|aaaadhp5ewo4eaaaaaaaaafs7q|axfo51x8x2ap' && echo "ABORT: tenancy namespace in staged diff" && exit 1
```

Better: install this as a pre-commit hook in `.git/hooks/pre-commit`. Local hook scripts are not tracked, so each developer must set it up — see your team's onboarding checklist for the exact script.

## What to do if you find a leak

1. **STOP** — do not add another commit thinking it will erase the original.
2. **Notify** — Slack/email whoever owns the repo immediately, name the file + commit hash + what leaked.
3. **Triage** — does it leak secrets (rotate) or only topology (history rewrite)?
4. **Remediate** — `git filter-repo --replace-text <redactions>` rewrites every affected commit in every branch. Force-push. Re-tag. Document the timeline.
5. **Prevent** — add the specific pattern to the pre-commit hook so it can't recur.

A worked example: `git filter-repo --replace-text` was run against this repo on 2026-05-19 to scrub leaked jumphost IP / OCIDs / tenancy namespace from `.planning/PHASE-8-BRIEF.md` and `.planning/STATUS-2026-05-19.md`. The redactions file is at `/tmp/redactions.txt` on that session's machine — don't commit it; copy useful patterns into the pre-commit hook instead.
