---
status: pending-discuss
proposed_date: 2026-05-19
created_by: phase-7-execute session
---

# Phase 8 Brief — Phoenix-Native Build + Registry Migration

This is a seed brief for `/gsd-discuss-phase 8`. It captures the user-confirmed scope and constraints discovered during the Phase 7 execute session so the discuss agent does not re-investigate.

## Goal

Cut cold-pull latency on `octo-apm-demo-oke` (us-phoenix-1) and remove cross-region OCIR transfer by:
1. Building images on a Phoenix VM (`octo-emdemo-jumphost-v5`, shape `VM.Standard.E5.Flex`, x86_64).
2. Pushing to `phx.ocir.io/${OCIR_TENANCY}/<repo>` instead of `eu-frankfurt-1.ocir.io/${OCIR_TENANCY}/<repo>`.
3. Repointing all deploy manifests + Helm values to phx.
4. Keeping frankfurt as fallback for at least 7 days post-migration.

## In-scope services + repos

Empty Phoenix repos already provisioned in `LogAnalytics` compartment (image_count: 0 today, populated by Phase 8):
- `phx.ocir.io/${OCIR_TENANCY}/octo-drone-shop`
- `phx.ocir.io/${OCIR_TENANCY}/octo-apm-java-demo`
- `phx.ocir.io/${OCIR_TENANCY}/octo-workflow-gateway`
- `phx.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal`
- `phx.ocir.io/${OCIR_TENANCY}/octo-traffic-generator` (Phase 7 deliverable — needs phx mirror)

## Locked decisions

- **Build host:** `octo-emdemo-jumphost-v5` (instance OCID `<JUMPHOST_INSTANCE_OCID>`). Public IP `<JUMPHOST_PUBLIC_IP>`. Boot volume size must be verified before tool install.
- **NSG:** `octo-emdemo-jumphost-nsg` (`<JUMPHOST_NSG_OCID>`) in `LogAnalytics` compartment. Currently allows tcp/22 from `<DEV_EGRESS_IP_OLD>/32` and tcp/2222 from `<DEV_EGRESS_IP_OLD>/32` + `<DEV_EGRESS_IP_OLDER>/32`. Phase 8 must add the developer's current egress (variable — capture at execute time).
- **Tools to install:** docker (or podman+buildah), oci-cli, git, rsync, jq, helm. Verify each is missing before installing — do not blindly reinstall.
- **Auth:** OCIR push uses an Auth Token (not API key). Generate from OCI Console → Identity → Users → Auth Tokens. Store on jumphost as `~/opc/.ocir-token` mode 0600. Never commit.
- **Tenancy rules:** Stay inside `LogAnalytics` compartment for any OCI mutation (NSG rules, instance config, image repos). See `~/.claude/CLAUDE.md` "OCI Tenancy Boundaries".
- **Build script default:** `deploy/oke/build-push-images.sh` already defaults `OCIR_REGION=us-phoenix-1`. The eu-frankfurt-1 history was an override during the Phase 7 execute session — Phase 8 brings actual builds back in line with the script default.

## Out of scope

- Decommissioning the eu-frankfurt-1 repos (keep as fallback for one week minimum).
- Migrating ObserveAI / enterprise-crm-portal-as-its-own-project / other consumers — only the octo-apm-demo image set is in Phase 8.
- Touching other OKE clusters in the emdemo tenancy (`cluster-n`, `cluster2-basic`, `cluster3` — not ours).
- Changing the base image OS (still Oracle Linux 8 / python:3.12-slim / k6 etc as today).

## Risk surface

| Item | Risk | Mitigation |
|---|---|---|
| Jumphost shared with other engineers | Medium — tool install may surprise them | Verify dedication: SSH and check `last`, `who`, `~/.bash_history`. If shared, install via user-local prefix or notify owners. |
| NSG mutation visible to other users | Low | Add /32 rule scoped to single developer IP; remove on session end if temporary. |
| Image tag collision (frankfurt vs phx with same tag) | Medium | Use date-tagged immutable tags (`obs-YYYYMMDDhhmmss`), never just `:latest` during transition. |
| Pod restart during rollout disrupts traffic-gen → APM signal blip | Low | Rolling deploy 1-pod-at-a-time, maxUnavailable=0. |
| Manifest replace miss → ImagePullBackOff | Medium | Pre-flight: `helm template … \| grep -c eu-frankfurt-1` should equal 0 after manifest edits. Block apply otherwise. |
| OCI auth token leak in build logs | High | Pipe token via stdin to `docker login --password-stdin`, never `--password <val>`. Audit `~/.bash_history` after session. |

## Proposed plans (planner agent should refine)

1. **08-01** — NSG + jumphost reachability (add ingress, verify SSH, capture sshd config + arch + disk).
2. **08-02** — Jumphost tool bootstrap (install docker/oci-cli/git/rsync/jq/helm via dnf; verify versions; configure docker daemon for OCIR).
3. **08-03** — OCIR auth on jumphost (Auth Token generation procedure documented, login pinned, secret hygiene checks).
4. **08-04** — Build pipeline pilot: octo-traffic-generator (rsync, build, push, verify pull from OKE node via `crictl pull`).
5. **08-05** — Build pipeline rollout: 4 application services (parameterized over `octo-drone-shop`, `octo-apm-java-demo`, `octo-workflow-gateway`, `enterprise-crm-portal`).
6. **08-06** — Manifest + Helm repoint (single-commit atomic change, `${OCIR_REGION}` default flip, sed-replace audit).
7. **08-07** — Rolling deploy + APM signal continuity verification (canary order: traffic-gen → java-demo → workflow-gateway → drone-shop → crm-portal; verify each service tile in APM before next).
8. **08-08** — Documentation + ADR: update global CLAUDE.md "Cloud-Based Docker Builds" to point at jumphost; ADR for region change; runbook for future image refreshes.

Optional: **08-09** — Frankfurt repo deprecation timeline (7-day soak, then mark frankfurt repos read-only in OCI Console).

## Success criteria (Nyquist)

1. `kubectl get pods -A -o jsonpath='{.items[*].spec.containers[*].image}' | tr ' ' '\n' | grep -c eu-frankfurt-1.ocir.io` returns **0** for octo-apm-demo namespaces (`octo-drone-shop`, `enterprise-crm-portal`, `octo-traffic`).
2. All 5 image repos in `phx.ocir.io/${OCIR_TENANCY}/*` have `image_count > 0`.
3. Cold-pull benchmark: `crictl pull phx.ocir.io/${OCIR_TENANCY}/octo-drone-shop:latest` from node <OKE_WORKER_PRIV_IP_1> completes in < 25% of the time required to pull the equivalent frankfurt tag.
4. APM "Last 30 minutes" dashboard shows all 8 services healthy throughout the rolling deploy (no service gap > 60s).
5. `mkdocs build --strict` passes; Phase 8 verifier marks PASS.
6. Frankfurt repos retain their tags as fallback; `helm rollback` to a frankfurt-pinned values revision is exercised during Phase 8 verify-work.

## How to resume

```bash
git checkout main
git merge gsd/phase-7-oke-autoscaling-and-stress-demo   # ship Phase 7 first
gsd-sdk query roadmap add-phase --number 8 --name "Phoenix-Native Build + Registry Migration"
/gsd-discuss-phase 8
# discuss agent reads this brief at .planning/PHASE-8-BRIEF.md and asks for any remaining clarifications
```
