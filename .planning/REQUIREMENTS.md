# Requirements: OCTO APM Demo — v1.2 (phoenix-build-migration)

**Defined:** 2026-05-19
**Milestone:** v1.2 — phoenix-build-migration
**Core Value:** Cut cold-pull latency on `octo-apm-demo-oke` (us-phoenix-1) by building + serving container images from the same OCI region as the OKE cluster. Eliminate cross-region OCIR transfer without disrupting demo continuity.

Seed brief: [`.planning/PHASE-8-BRIEF.md`](./PHASE-8-BRIEF.md) — captures locked decisions, in-scope services, risk surface, and 8 plan stubs from the Phase 7 execute session.

## Current Requirements

### Phoenix-Native Build Pipeline

- [ ] **BUILD-01**: All 5 octo-apm-demo image repos exist in `phx.ocir.io/${OCIR_TENANCY}/*` with `image_count > 0` for the head tag:
  `octo-drone-shop`, `octo-apm-java-demo`, `octo-workflow-gateway`, `enterprise-crm-portal`, `octo-traffic-generator`. Frankfurt repos (`eu-frankfurt-1.ocir.io/${OCIR_TENANCY}/*`) retain their existing tags as rollback fallback for at least 7 days post-cutover.
- [ ] **BUILD-02**: A reproducible build pipeline runs natively on `octo-emdemo-jumphost-v5` (Phoenix, x86_64). The pipeline:
  - Authenticates to OCIR via Auth Token (never API key in build env).
  - Builds each image with `--platform linux/amd64`, immutable date-tagged (`obs-YYYYMMDDhhmmss`) plus `latest` alias.
  - Pushes to phx OCIR with `docker push --password-stdin` to keep tokens out of shell history.
  - Is idempotent (re-runs are safe) and documented in a runbook checked into the repo.
- [ ] **BUILD-03**: All deploy manifests + Helm values default to `phx.ocir.io/${OCIR_TENANCY}/*`. The build-script default (`OCIR_REGION=us-phoenix-1` already in `deploy/oke/build-push-images.sh`) is the source of truth. A pre-commit / pre-deploy gate (`grep -c eu-frankfurt-1.ocir.io | matches deploy/`) returns 0 for octo-apm-demo namespaces. Operator override remains possible via `OCIR_REGION=eu-frankfurt-1` env var for rollback.

### Rollout Continuity

- [ ] **BUILD-04**: Rolling deploy of all 5 services to `octo-apm-demo-oke` keeps every service visible in the OCI APM Service Monitoring view throughout the cutover (no service gap longer than 60s in the Last 30 minutes window). Canary order: `octo-traffic-generator` → `octo-apm-java-demo` → `octo-workflow-gateway` → `octo-drone-shop` → `enterprise-crm-portal`. Each step verifies the next service tile is healthy before continuing.
- [ ] **BUILD-05**: Cold-pull latency benchmark on a fresh OKE worker node: `crictl pull phx.ocir.io/${OCIR_TENANCY}/octo-drone-shop:<head-tag>` completes in **< 25%** of the wall-clock time for the equivalent `eu-frankfurt-1.ocir.io/${OCIR_TENANCY}/octo-drone-shop:<head-tag>` pull. Measured on the same node, same network conditions, both pulls cold (image not cached).

### Operability + Rollback

- [ ] **BUILD-06**: Helm rollback to a frankfurt-pinned values revision is exercised during verify-work and documented in the runbook. A single `helm rollback <release> <prev-revision>` returns the cluster to the frankfurt image set within 5 min.
- [ ] **BUILD-07**: Global CLAUDE.md "Cloud-Based Docker Builds" section updated: jumphost becomes the primary build host; `control-plane-oci` (frankfurt) remains the fallback. ADR captured under `docs/adr/` documenting the region migration rationale.

## Deferred Requirements

- **FUTURE-04**: Decommission eu-frankfurt-1 repos. Out of scope for v1.2 — frankfurt stays as fallback for ≥7 days. A future milestone may mark frankfurt repos read-only in OCI Console.
- **FUTURE-05**: Application-level Prometheus exposition + mgmt-agent scrape config for Stack Monitoring metric coverage. Separate phase (likely v1.3 or v1.4) — does not gate v1.2.
- **FUTURE-06**: OKE cluster ops hardening (boot volume resize 36→100GB, daily `crictl` GC cron, `oci-onm-mgmt-agent` clean-reinstall to surface CPU/memory metrics). Promoted to a separate "infra-hardening" milestone.
- **FUTURE-07**: Migration of ObserveAI / enterprise-crm-portal-as-its-own-project / other consumers of `eu-frankfurt-1.ocir.io/${OCIR_TENANCY}/*`. Only octo-apm-demo images are in v1.2.

## Out of Scope

| Feature | Reason |
|---|---|
| Cross-region replication of OCIR via OCI-native tooling | OCIR doesn't support pull-through caches between regions; v1.2 uses dual-push (frankfurt + phoenix) during the soak window instead. |
| Changing the base image OS or runtime | Image content stays bit-identical; only the registry endpoint changes. |
| Touching other engineers' OKE clusters (`cluster-n`, `cluster2-basic`, `cluster3`) | Per `~/.claude/CLAUDE.md` tenancy rules — only `octo-apm-demo-oke` is in scope. |
| Real OCID / IP / tenancy namespace inlined in any committed file | Per `.planning/SECURITY.md` — use `<PLACEHOLDER>` tokens, resolve via `~/.claude/private/octo-apm-redactions.md`. |

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| BUILD-01, BUILD-02, BUILD-03 | Phase 8 | Planned |
| BUILD-04, BUILD-05 | Phase 8 | Planned |
| BUILD-06, BUILD-07 | Phase 8 | Planned |

**Coverage:**
- Current requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0

---
*Requirements defined: 2026-05-19 — derived from `.planning/PHASE-8-BRIEF.md`*
