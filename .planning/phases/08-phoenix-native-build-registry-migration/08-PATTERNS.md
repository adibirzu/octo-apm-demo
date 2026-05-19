# Phase 8: Phoenix-Native Build + Registry Migration — Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 14 files-to-create-or-modify across 8 plan stubs
**Analogs found:** 14 / 14 (every Phase 8 target has at least one existing repo analog)

Binding security rule: every file written or modified in Phase 8 MUST follow `.planning/SECURITY.md` — no real OCIDs, public IPs, tenancy registry namespace, or LA namespace inline. Use `<UPPERCASE_PLACEHOLDER>` tokens or `${ENV_VAR}` references that resolve at runtime.

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `deploy/oke/build-push-images.sh` (modify) | build pipeline / shell | batch + transform | self (in-place edit) | exact |
| `deploy/oke/jumphost-bootstrap.sh` (new) | operator-gated shell | event-driven (install) | `deploy/oke/bootstrap-emdemo-secrets.sh` | role-match |
| `deploy/oke/ocir-login.sh` (new) | operator-gated shell | request-response (auth) | `tools/monitoring-alarms/apply.sh` | role-match |
| `deploy/oke/build-push-images-phoenix.sh` (new wrapper, optional) | shell wrapper | batch | `deploy/oke/build-push-images.sh` | exact |
| `deploy/helm/octo-apm-demo/values.yaml` (modify) | Helm config | config | self | exact |
| `deploy/helm/octo-apm-demo/templates/_helpers.tpl` (no change expected — verify) | Helm template helper | transform | self | exact |
| `deploy/k8s/oke/shop/deployment.yaml` (no source change — verify envsubst) | raw manifest | request-response | self | exact |
| `deploy/k8s/oke/crm/deployment.yaml` (no source change — verify envsubst) | raw manifest | request-response | `deploy/k8s/oke/shop/deployment.yaml` | exact |
| `deploy/k8s/oke/apm-java-demo/deployment.yaml` (no source change — verify) | raw manifest | request-response | `deploy/k8s/oke/shop/deployment.yaml` | exact |
| `deploy/k8s/oke/workflow-gateway/deployment.yaml` (no source change — verify) | raw manifest | request-response | `deploy/k8s/oke/shop/deployment.yaml` | exact |
| `tools/traffic-generator/k8s/deployment.yaml` (no source change — verify envsubst) | raw manifest | request-response | `deploy/k8s/oke/shop/deployment.yaml` | exact |
| `site/operations/phoenix-build-runbook.md` (new) | runbook / docs | docs | `site/operations/stress-demo-lb-routing.md` | exact |
| `docs/adr/0001-phoenix-region-migration.md` (new — directory does not yet exist) | ADR / docs | docs | `site/operations/stress-demo-lb-routing.md` (closest in-repo prose pattern) | partial |
| `~/.claude/CLAUDE.md` "Cloud-Based Docker Builds" section (modify — outside repo) | global operator config | docs | self (existing section) | exact |

---

## Pattern Assignments

### Plan 08-01 — NSG + jumphost reachability

**No new files in the repo for this plan.** This is an operator-time OCI mutation captured in the runbook (08-08) only. PATTERNS guidance:

- **Use `oci network nsg ...` CLI from `OCI_CLI_PROFILE=emdemo`**, scoped to `LogAnalytics` compartment. The "scope to one compartment" pattern is already enforced by `deploy/oke/build-push-images.sh:64-79` (`--compartment-id` always passed, never tenancy-root).
- **Add /32 ingress for current dev egress only**, never `0.0.0.0/0`. Document the source IP as `<DEV_EGRESS_IP_CURRENT>` in the runbook — never inline.
- **Removal step required** at session end (or document the soak window). Mirror the cleanup ethos in `tools/monitoring-alarms/apply.sh:91` (`trap 'rm -rf "${TMPDIR_OUT}"' EXIT`) — leave no residue.

---

### Plan 08-02 — Jumphost tool bootstrap (new file: `deploy/oke/jumphost-bootstrap.sh`)

**Analog:** `deploy/oke/bootstrap-emdemo-secrets.sh`

**Header + usage pattern** (`deploy/oke/bootstrap-emdemo-secrets.sh:1-31`):
```bash
#!/usr/bin/env bash
# <one-line purpose>
#
# <multi-line context describing inputs/outputs>

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy/oke/jumphost-bootstrap.sh
...
EOF
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    "") ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac
```

**`require_tool` / "verify before install" pattern** (`deploy/oke/build-push-images.sh:54-59`):
```bash
require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}
```
For 08-02 invert the polarity: `command -v docker >/dev/null 2>&1 || sudo dnf install -y docker-ce`. Do **not** blindly reinstall — the brief explicitly says jumphost may be shared.

**Idempotency / upsert pattern** (`deploy/oke/build-push-images.sh:61-81` — `ensure_repo`): query-then-create. Apply to package install (query rpm/dnf list before install) and to docker-daemon config (test connectivity before rewriting `daemon.json`).

**No secret printing** (`deploy/oke/bootstrap-emdemo-secrets.sh:11-12, 275`): script must end with explicit "Secret values were not printed." line. For 08-02, the OCIR auth token must never appear in stdout or `~/.bash_history`.

---

### Plan 08-03 — OCIR auth on jumphost (new file: `deploy/oke/ocir-login.sh`)

**Analog:** `tools/monitoring-alarms/apply.sh` + `deploy/oke/bootstrap-emdemo-secrets.sh:230-242` (the docker-registry secret block).

**Token-via-stdin pattern (CRITICAL — required by BUILD-02):**
```bash
# Correct — token sourced from file mode 0600, piped via stdin:
docker login --username "${OCIR_USERNAME}" \
    --password-stdin "${OCIR_REGION}.ocir.io" \
    < "${HOME}/.ocir-token"

# WRONG — never:
#   docker login -p "$TOKEN" ...
#   docker login --password "$TOKEN" ...
```

**Existing reference (`deploy/oke/bootstrap-emdemo-secrets.sh:230-242`)** for the kubectl-side equivalent. See the file directly for the exact lines; the relevant shape is summarized below to keep this PATTERNS doc free of credential-shaped strings:

- A function `apply_ocir_secret_if_available <namespace>` guards on three env vars being set: `OCIR_REGION`, `OCIR_USERNAME`, `OCIR_AUTH_TOKEN`.
- When all three are present, it runs `kubectl -n <ns> create secret docker-registry ocir-pull-secret` with `--docker-server`, `--docker-username`, and `--docker-password` flags whose VALUES are env-var references (not inline literals), piped through `--dry-run=client -o yaml | kubectl apply -f -`.
- Phase 8 plans reusing this shape MUST keep the env-var-reference discipline (never inline a token value) and quote the source file by line range rather than copying the literal flag block into a tracked doc.

**Token file convention** (from 08-CONTEXT.md): store as `~/.ocir-token` mode 0600 on the jumphost. New script must `chmod 600` immediately after write, fail loudly if mode is not 0600 on read.

**Mode-0600 enforcement pattern** to add (no exact analog in repo — derive from common bash idiom):
```bash
require_mode() {
    local f="$1" want="$2"
    local got
    got="$(stat -c '%a' "$f" 2>/dev/null || stat -f '%Lp' "$f")"
    [[ "$got" == "$want" ]] || { echo "ERROR: $f mode is $got, want $want" >&2; exit 1; }
}
require_mode "${HOME}/.ocir-token" 600
```

---

### Plan 08-04 — Build pipeline pilot (octo-traffic-generator)

**Modify** `deploy/oke/build-push-images.sh` to accept a `--service traffic-generator` selector (or factor `build_push` into a single-service entrypoint). All current logic is the analog — preserve:

**Build-push core pattern** (`deploy/oke/build-push-images.sh:83-103`):
```bash
build_push() {
    local repo="$1"
    local dockerfile="$2"
    local context="$3"
    local image="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/${repo}:${IMAGE_TAG}"
    local latest="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/${repo}:latest"
    local tags=(-t "${image}")
    if [[ "${PUSH_LATEST}" == "true" ]]; then
        tags+=(-t "${latest}")
    fi
    if [[ "${BUILDER}" == "docker" ]]; then
        docker buildx build --platform "${PLATFORM}" -f "${dockerfile}" "${tags[@]}" --push "${context}"
    else
        podman build --platform "${PLATFORM}" -f "${dockerfile}" "${tags[@]}" "${context}"
        podman push "${image}"
    fi
}
```

**Defaults to preserve** (`deploy/oke/build-push-images.sh:42-52`):
```bash
: "${OCI_PROFILE:=emdemo}"
: "${OCIR_REGION:=us-phoenix-1}"   # ← already correct, do NOT regress
: "${OCIR_TENANCY:=$(oci os ns get --profile "${OCI_PROFILE}" --query data --raw-output)}"
: "${IMAGE_TAG:=$(date -u +%Y%m%d%H%M%S)}"
: "${PLATFORM:=linux/amd64}"
: "${PUSH_LATEST:=false}"
```

**`--password-stdin` for docker push:** the script today relies on caller having already logged in (`docker buildx ... --push`). For 08-04, the jumphost runbook must call `deploy/oke/ocir-login.sh` first; do not embed `docker login` inside the loop.

**Verify-on-OKE-node step (new):** mirror `verify_runtime_uid` (`deploy/oke/build-push-images.sh:105-136`) — same fail-fast shape, but invoking `crictl pull` from an OKE worker via `kubectl debug node/...` or SSH. This is the BUILD-05 cold-pull benchmark.

**Idempotent repo-create** (`deploy/oke/build-push-images.sh:61-81` `ensure_repo`): keep as-is — it queries `oci artifacts container repository list` first and creates only if absent. The empty phx repos in `LogAnalytics` compartment will be picked up by display-name match.

---

### Plan 08-05 — Build pipeline rollout (4 application services)

Same pattern as 08-04 — no new files. The existing for-loop in `deploy/oke/build-push-images.sh:165-176` already enumerates `octo-drone-shop enterprise-crm-portal octo-apm-java-demo octo-workflow-gateway`. Plan 08-05 just runs it end-to-end on the Phoenix jumphost.

**Add `octo-traffic-generator` to the build loop** if it isn't already (search for the `build_push octo-traffic-generator` line — Phase 7 may or may not have added it). The analog for `build_push` invocation is `deploy/oke/build-push-images.sh:169-176`:
```bash
build_push octo-drone-shop "${REPO_ROOT}/shop/Dockerfile" "${REPO_ROOT}"
verify_runtime_uid octo-drone-shop "${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${IMAGE_TAG}"
...
```

Traffic-generator's Dockerfile pattern follows `tools/stress-runner/Dockerfile:7-12` (multi-stage, ARG-driven base, build command in header comment) — extend the comment in any new Dockerfile to call out the **jumphost** as build host (replacing `control-plane-oci`):
```
# Build (per global cloud-build rule — run on Phoenix jumphost):
#   ssh octo-emdemo-jumphost-v5 "cd /tmp/octo-apm-demo && \
#       docker build -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/<repo>:$(date +%Y%m%d%H%M%S) ."
```

---

### Plan 08-06 — Manifest + Helm repoint

**Source-of-truth flip** in `deploy/helm/octo-apm-demo/values.yaml:18,29`:

Current (lines 14-33):
```yaml
global:
  dnsDomain: example.com
  ociRegion: eu-frankfurt-1            # ← line 18, flip to us-phoenix-1
  ...
  image:
    region: eu-frankfurt-1             # ← line 29, flip to us-phoenix-1
    tenancy: ""
    tag: latest
    pullPolicy: IfNotPresent
    pullSecretName: ocir-pull-secret
```

**Image resolution helper** (`deploy/helm/octo-apm-demo/templates/_helpers.tpl:37-51`) — already does the right thing, no change needed:
```gotmpl
{{- define "octo.image" -}}
{{- $ctx := index . 0 -}}
{{- $cmp := index . 1 -}}
{{- $region := default $ctx.Values.global.image.region $cmp.image.region -}}
{{- $tenancy := default $ctx.Values.global.image.tenancy $cmp.image.tenancy -}}
{{- $tag := toString (default $ctx.Values.global.image.tag $cmp.image.tag) -}}
{{- if not $tenancy -}}{{- fail "global.image.tenancy is required" -}}{{- end -}}
{{- printf "%s.ocir.io/%s/%s:%s" (toString $region) (toString $tenancy) (toString $cmp.image.repository) $tag -}}
{{- end -}}
```
Plan 08-06 only changes the **default** in `values.yaml`; this helper continues to work unchanged.

**Raw manifests:** all five `deploy/k8s/oke/*/deployment.yaml` plus `tools/traffic-generator/k8s/deployment.yaml` already use `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/<repo>:${IMAGE_TAG}` (confirmed by `grep -n` — see file list above). **No source edits required**; only the operator's `OCIR_REGION` env var changes, and that already defaults to `us-phoenix-1` in `build-push-images.sh`. The pre-deploy gate from BUILD-03 verifies post-render output.

**Pre-deploy guard (new addition to runbook, no script file required):**
```bash
# Required by BUILD-03 — block the apply if any frankfurt residue remains:
helm template octo-apm-demo deploy/helm/octo-apm-demo -f deploy/helm/octo-apm-demo/values.yaml \
    | grep -c 'eu-frankfurt-1\.ocir\.io' \
    | { read n; [[ "$n" == "0" ]] || { echo "ABORT: frankfurt OCIR refs still present: $n"; exit 1; }; }
```

**Audit current residue (single known offender):**
- `deploy/k8s/shop/secret-provider-class.yaml:45` — comment only ("Region slug without the ocir.io suffix, e.g. eu-frankfurt-1"). **Update the comment** to read `e.g. us-phoenix-1`, no functional change needed.

---

### Plan 08-07 — Rolling deploy + APM signal continuity

**No new files.** This is operator + verification. Pattern guidance:

- **Canary order from BUILD-04** (`.planning/REQUIREMENTS.md:24`): `octo-traffic-generator → octo-apm-java-demo → octo-workflow-gateway → octo-drone-shop → enterprise-crm-portal`. One service at a time, `kubectl set image deployment/<name> <container>=<phx-image>` then wait `kubectl rollout status` before the next.
- **maxUnavailable=0 already set** in `deploy/k8s/oke/shop/deployment.yaml:24-27`:
  ```yaml
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  ```
  Verify the same block exists in CRM, java-demo, workflow-gateway, traffic-gen manifests before rolling.
- **Helm rollback drill (BUILD-06):** the runbook (08-08) must include `helm rollback <release> <prev-revision>` exercised live during verify-work. Pattern: keep the pre-cutover revision number visible (`helm history`), document it in the rollout audit comment, exercise rollback once before declaring success.

---

### Plan 08-08 — Documentation + ADR

#### Runbook (new file: `site/operations/phoenix-build-runbook.md`)

**Analog:** `site/operations/stress-demo-lb-routing.md` (Phase 7 runbook — most recent same-shape artifact).

**Header pattern** (`site/operations/stress-demo-lb-routing.md:1-13`):
```markdown
# <Title> — <Subsystem> Runbook

Operator runbook for <one-sentence purpose>.

<2-3 sentences of context: what contract this preserves, when to run, why now>.

## When to apply
## Prerequisites           ← table of required env vars (placeholder-only)
## Steps                   ← numbered, each with bash block + "Notes" body text
## Verify                  ← curl / kubectl probes
## Rollback                ← always present, two options if possible
## Audit + recording       ← workshop run_id, change-management PR comment
```

**Prerequisites-table pattern** (`site/operations/stress-demo-lb-routing.md:24-31`):
```markdown
| Item | How to set | Notes |
|---|---|---|
| `OCTO_LB_OCID` | `export OCTO_LB_OCID="<ocid-of-octo-LB>"` | Placeholder — never commit a live OCID. Source from your tenancy's terraform output `lb_id`. |
```
For Phase 8, replicate with rows for `JUMPHOST_PUBLIC_IP`, `JUMPHOST_INSTANCE_OCID`, `OCIR_REGION`, `OCIR_TENANCY`, `OCIR_USERNAME`, `LOGANALYTICS_COMPARTMENT_OCID` — **placeholder tokens only, never real values** (per `.planning/SECURITY.md:9-18`).

**Dry-run-before-apply gating** (`site/operations/stress-demo-lb-routing.md:78-93`): show the `--dry-run` invocation first, then the live-apply with explicit operator confirmation. For Phase 8, the equivalent is `docker buildx build` (which always pushes when `--push` is set) — instead gate at the `docker login` step ("you have just logged in — verify with `docker info | grep -i registry` before pushing").

**Rollback section** (`site/operations/stress-demo-lb-routing.md:110-132`): always two options — A is the standard rollback (re-point `OCIR_REGION=eu-frankfurt-1` and `helm rollback`); B is the last-resort manual `kubectl set image` to a known-good frankfurt SHA per service.

#### ADR (new directory + file: `docs/adr/0001-phoenix-region-migration.md`)

**`docs/adr/` directory does not yet exist** — Phase 8 creates it. No exact in-repo analog; closest prose pattern is `site/operations/stress-demo-lb-routing.md` (same author voice, same redaction discipline).

**Standard ADR shape** (no template in repo; follow Michael Nygard's canonical form, lifted from common practice):
```markdown
# ADR 0001: Phoenix-Native Build + Registry for octo-apm-demo

- **Status:** Accepted
- **Date:** 2026-05-19
- **Deciders:** <ROLE-only, no personal names per .planning/SECURITY.md>

## Context
<2-3 paragraphs. Cite BUILD-01..07 requirement IDs. Reference the cross-region
cold-pull problem without quoting real IPs/IPs of OKE workers — use
<OKE_WORKER_PRIV_IP> placeholders.>

## Decision
<1 paragraph: build on octo-emdemo-jumphost-v5 in us-phoenix-1, push to
phx.ocir.io/${OCIR_TENANCY}/*, default OCIR_REGION=us-phoenix-1, keep
frankfurt as ≥7-day fallback.>

## Consequences
- Positive: <cold-pull latency reduction, single-region failure domain>
- Negative: <jumphost becomes a build SPOF — mitigation: control-plane-oci
  in frankfurt remains the documented fallback per CLAUDE.md>
- Neutral: <image content bit-identical, only registry endpoint changes>

## Alternatives considered
- OCIR cross-region replication (not supported by service today)
- Build locally with QEMU emulation (rejected — see global CLAUDE.md
  "Cloud-Based Docker Builds" rule)
- Keep status quo with frankfurt builds (rejected — fails BUILD-05)

## References
- `.planning/REQUIREMENTS.md` BUILD-01..07
- `~/.claude/CLAUDE.md` "Cloud-Based Docker Builds & Deployments" section
- `deploy/oke/build-push-images.sh` (build pipeline source of truth)
```

#### Global CLAUDE.md update (outside repo: `~/.claude/CLAUDE.md`)

Not committable to this repo — operator-side change. Pattern: the existing "Cloud-Based Docker Builds & Deployments" section in `~/.claude/CLAUDE.md` (loaded via the system reminder at the top of this session) already has the right shape — Phase 8 edits the "Preferred: Build on Control Plane VM" subsection to make **`octo-emdemo-jumphost-v5`** the primary and **`control-plane-oci`** the fallback, with a one-line note about region selection (phx for octo-apm-demo, frankfurt for ObserveAI / enterprise-crm-portal-as-its-own-project).

---

### Plan 08-09 (optional) — Frankfurt repo deprecation

If included, no new file — operator-time change in OCI Console (mark repos read-only). Document in the runbook (08-08) under a "Soak window + deprecation" final section. Pattern: same "wait N days, then mutate" cadence as `tools/monitoring-alarms/apply.sh` confirm-phrase gate (`APPLY=true` + interactive prompt).

---

## Shared Patterns (apply to multiple Phase 8 files)

### A. Operator-gated apply.sh — `APPLY=false` default + interactive confirm

**Source:** `tools/monitoring-alarms/apply.sh:44-46, 116-121` and `tools/apm-saved-queries/apply.sh:43-44, 84-97`.

**Apply to:** every new shell script in `deploy/oke/` that mutates jumphost state or OCIR (i.e. `jumphost-bootstrap.sh`, `ocir-login.sh`, and any wrapper that issues `oci ...` calls beyond read-only `list/get`).

**Excerpt to copy** (`tools/monitoring-alarms/apply.sh:44-46, 105-121`):
```bash
: "${OCI_PROFILE:=emdemo}"
: "${APPLY:=false}"
: "${COMPARTMENT_ID:?COMPARTMENT_ID is required — set to the OCTO compartment OCID}"

# ... dry-run preview happens here ...

if [[ "${APPLY}" != "true" ]]; then
    echo "DRY-RUN: would call '<verb>' for each <object> above."
    echo "Re-run with APPLY=true to mutate."
    exit 0
fi

echo "About to MUTATE <subsystem> in compartment ${COMPARTMENT_ID:0:24}…"
read -r -p "Type 'APPLY' to confirm: " confirm
if [[ "${confirm}" != "APPLY" ]]; then
    echo "Aborted — confirm phrase did not match."
    exit 1
fi
```

Note: `deploy/oke/build-push-images.sh` itself is **not** APPLY-gated today because its only mutation is image push (idempotent, identified by tag). Phase 8 does **not** retrofit APPLY-gating onto it — but any new mutator (NSG rules, OCIR auth-token rotation) gets the gate.

### B. envsubst rendering with placeholder leakage guard

**Source:** `tools/monitoring-alarms/apply.sh:93-103`.

**Apply to:** any new template file that `envsubst` consumes (deploy manifests already use this — `deploy/oke/bootstrap-emdemo-secrets.sh:262`).

```bash
TMPDIR_OUT="$(mktemp -d -t monitoring-alarms-XXXXXX)"
trap 'rm -rf "${TMPDIR_OUT}"' EXIT

for f in "${files[@]}"; do
    base="$(basename "$f")"
    envsubst < "$f" > "${TMPDIR_OUT}/${base}"
    if grep -q '\${[A-Z_]*}' "${TMPDIR_OUT}/${base}"; then
        echo "ERROR: unresolved envsubst placeholder in ${base}" >&2
        grep '\${[A-Z_]*}' "${TMPDIR_OUT}/${base}" >&2
        exit 1
    fi
done
```

For Phase 8, the equivalent assertion for Helm output is `helm template ... | grep -c 'eu-frankfurt-1\.ocir\.io' == 0` (BUILD-03 gate, captured under Plan 08-06 above).

### C. Compartment scoping — never tenancy-root mutations

**Source:** `deploy/oke/build-push-images.sh:64-79, 147-151` (every OCI CLI mutation passes `--compartment-id` from `outputs.json`).

**Apply to:** every `oci ...` call in any new Phase 8 script. The compartment is always `LogAnalytics` (from 08-CONTEXT.md). Read it from `credentials/emdemo/outputs.json`:
```bash
COMPARTMENT_ID="$(jq -r '.deployment_compartment_id.value' "${OUTPUTS_FILE}")"
[[ -n "${COMPARTMENT_ID}" && "${COMPARTMENT_ID}" != "null" ]] || {
    echo "Could not read deployment compartment id from ${OUTPUTS_FILE}" >&2; exit 1
}
```

### D. "Never print secret values" + bash-history hygiene

**Source:** `deploy/oke/bootstrap-emdemo-secrets.sh:11-12, 275`.

**Apply to:** `deploy/oke/ocir-login.sh` (08-03). Specifically:
- Token file is sourced via shell redirection (`< "${HOME}/.ocir-token"`), never `cat` to a variable that could be echoed.
- Script must end with: `echo "Done. OCIR auth token was not printed."`.
- Runbook (08-08) must include a final step: `unset HISTFILE` for the session, or run inside `env HISTFILE=/dev/null bash`. **Audit `~/.bash_history` at the end** of the jumphost session (per 08-CONTEXT.md risk-surface row 6).

### E. Image immutability — refuse `IMAGE_TAG=latest` by default

**Source:** `deploy/oke/build-push-images.sh:50-52, 153-156`.
```bash
: "${ALLOW_LATEST_IMAGE_TAG:=false}"
if [[ "${IMAGE_TAG}" == "latest" && "${ALLOW_LATEST_IMAGE_TAG}" != "true" ]]; then
    echo "Refusing to publish mutable image tag 'latest'." >&2
    exit 1
fi
```
Phase 8 inherits this — every phx-OCIR push gets a date-tagged immutable identifier (`obs-YYYYMMDDhhmmss` per the brief). The `latest` alias is gated behind `PUSH_LATEST=true` and `ALLOW_LATEST_IMAGE_TAG=true`. Do not relax.

### F. Placeholder discipline (binding rule from `.planning/SECURITY.md`)

**Applies to every Phase 8 file**, including PATTERNS.md itself.

Token table (from `.planning/SECURITY.md:9-18`) — use these in any new prose, runbook, ADR, or script comment:

| What | Placeholder |
|---|---|
| Jumphost instance OCID | `<JUMPHOST_INSTANCE_OCID>` |
| Jumphost public IP | `<JUMPHOST_PUBLIC_IP>` |
| Jumphost NSG OCID | `<JUMPHOST_NSG_OCID>` |
| Developer egress (current session) | `<DEV_EGRESS_IP_CURRENT>` |
| Developer egress (historical) | `<DEV_EGRESS_IP_OLD>`, `<DEV_EGRESS_IP_OLDER>` |
| LogAnalytics compartment OCID | `<LOGANALYTICS_COMPARTMENT_OCID>` |
| Tenancy registry namespace | `${OCIR_TENANCY}` (always env-var, never inline) |
| OCIR auth-token username | `${OCIR_USERNAME}` |
| OCIR region | `${OCIR_REGION}` |
| OKE cluster OCID | `<OKE_CLUSTER_OCID>` |
| OKE worker private IP | `<OKE_WORKER_PRIV_IP_1>` etc. |
| APM domain OCID | `<APM_DOMAIN_ID>` |

Pre-commit grep (operator side, lives at `~/.claude/private/octo-apm-redactions.md`) catches `ocid1\.[a-z]+\.oc1\.<region>\.[a-z0-9]{40,}`, public OCI IP ranges, and the 12-char tenancy namespace. **The planner agent must instruct every plan to leave outputs.json / .env files out of any committed example block.**

---

## No Analog Found

| File | Role | Reason |
|---|---|---|
| `docs/adr/` directory | docs root | Repo currently has no ADR directory; Phase 8 creates the first one. Use canonical Michael-Nygard ADR shape (template provided inline above under Plan 08-08). |
| Mode-0600 enforcement on `~/.ocir-token` | shell guard | No exact in-repo precedent for `stat`/`chmod` enforcement. Pattern provided inline under Plan 08-03. |
| `crictl pull` benchmark from an OKE worker | verification | No existing script invokes `crictl` against worker nodes. Closest analog is `verify_runtime_uid` in `deploy/oke/build-push-images.sh:105-136` (fail-fast verification on a freshly pushed image) — reuse the same exit-on-mismatch shape, but the harness has to reach the worker (via `kubectl debug node/<name>` or SSH bastion path). Planner agent should call this out as a small new utility in Plan 08-04 or 08-07. |

---

## Metadata

**Analog search scope:** `deploy/oke/`, `deploy/helm/octo-apm-demo/`, `deploy/k8s/oke/`, `tools/*/apply.sh`, `tools/traffic-generator/k8s/`, `tools/stress-runner/`, `site/operations/`, `.planning/`.
**Files scanned:** ~40 (sampled the highest-signal subset per the early-stopping rule).
**Pattern extraction date:** 2026-05-19.
