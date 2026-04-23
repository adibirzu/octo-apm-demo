#!/usr/bin/env bash
# Download the OCI APM Java agent zip into services/apm-java-demo/agent-bundle/.
#
# Two paths — auto-detected:
#
#   LOCAL    — if `oci apm-control-plane install agent-installer ...` works
#              with your user's OCI config (you have `read apm-domains`
#              permission in the tenancy).
#
#   VIA-POD  — fallback when local CLI lacks grants. Execs into the live
#              shop pod (which has instance-principal grants via the
#              octo-oke-workers dynamic group) to fetch the zip, then
#              `kubectl cp` pulls it back to the host.
#
# Usage:
#   OCI_APM_COMPARTMENT_ID=ocid1.compartment.oc1..xxx \
#   OCI_APM_DOMAIN_ID=ocid1.apmdomain.oc1..xxx \
#     ./services/apm-java-demo/download-agent.sh
#
# On success, prints the path to the bundled zip and exits 0. The deploy
# script picks it up automatically on the next build.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${SCRIPT_DIR}/agent-bundle/apm-java-agent.zip"
: "${OCI_APM_COMPARTMENT_ID:?Set OCI_APM_COMPARTMENT_ID}"
: "${OCI_APM_DOMAIN_ID:?Set OCI_APM_DOMAIN_ID (e.g. ocid1.apmdomain.oc1..xxx)}"

mkdir -p "$(dirname "${DEST}")"

_try_local() {
    if ! command -v oci >/dev/null 2>&1; then
        echo "[local] oci CLI not found — skipping"
        return 1
    fi

    # 1. Pick the first ENABLED Java agent installer for this APM domain.
    installer_id=$(oci apm-control-plane install agent-installer list \
        --compartment-id "${OCI_APM_COMPARTMENT_ID}" \
        --apm-domain-id "${OCI_APM_DOMAIN_ID}" \
        --agent-installer-type JAVA_AGENT \
        --all 2>/dev/null \
      | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin).get('data', [])
except Exception:
    sys.exit(1)
for item in data:
    if item.get('lifecycle-state') == 'ACTIVE':
        print(item['id']); break
" 2>/dev/null || true)

    if [[ -z "${installer_id}" ]]; then
        echo "[local] no JAVA_AGENT installer found via local CLI"
        return 1
    fi

    # 2. Download the binary.
    oci apm-control-plane install agent-installer-download \
        --agent-installer-id "${installer_id}" \
        --file "${DEST}" 2>&1 | tail -3
    [[ -s "${DEST}" ]]
}

_try_via_pod() {
    if ! command -v kubectl >/dev/null 2>&1; then
        echo "[via-pod] kubectl not found — skipping"
        return 1
    fi
    local ns="${K8S_NAMESPACE:-octo-drone-shop}"
    local pod
    pod=$(kubectl get po -n "${ns}" -l app=octo-drone-shop \
        --field-selector=status.phase=Running \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -z "${pod}" ]]; then
        echo "[via-pod] no Running shop pod in ${ns}"
        return 1
    fi

    echo "[via-pod] using ${ns}/${pod}"
    kubectl exec -n "${ns}" "${pod}" -- python3 - <<PYEOF
import os, sys, oci
signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
c = oci.apm_control_plane.AgentInstallerClient(config={}, signer=signer)
try:
    lst = c.list_agent_installers(
        compartment_id="${OCI_APM_COMPARTMENT_ID}",
        apm_domain_id="${OCI_APM_DOMAIN_ID}",
        agent_installer_type="JAVA_AGENT",
    ).data
except Exception as exc:
    print("LIST_ERR", exc, file=sys.stderr)
    sys.exit(2)

candidates = [i for i in getattr(lst, "items", lst) if getattr(i, "lifecycle_state", "ACTIVE") == "ACTIVE"]
if not candidates:
    print("NO_INSTALLER", file=sys.stderr); sys.exit(3)

inst = candidates[0]
print("[via-pod] installer id=%s" % inst.id, file=sys.stderr)
resp = c.download_agent_installer(agent_installer_id=inst.id)
with open("/tmp/apm-java-agent.zip", "wb") as fp:
    for chunk in resp.data.raw.stream(65536, decode_content=False):
        fp.write(chunk)
print("WROTE /tmp/apm-java-agent.zip", os.path.getsize("/tmp/apm-java-agent.zip"))
PYEOF

    kubectl cp "${ns}/${pod}:/tmp/apm-java-agent.zip" "${DEST}" 2>&1 | tail -3
    kubectl exec -n "${ns}" "${pod}" -- rm -f /tmp/apm-java-agent.zip >/dev/null 2>&1 || true
    [[ -s "${DEST}" ]]
}

echo "Destination: ${DEST}"
if _try_local; then
    echo "[OK] fetched via local OCI CLI"
elif _try_via_pod; then
    echo "[OK] fetched via Running shop pod (instance-principal)"
else
    cat >&2 <<EOF

Neither path succeeded. Manual fallback:
  1. OCI Console → Observability & Management → APM → <your APM domain>
     → Agent Registration Keys → Java → Download
  2. Save as: ${DEST}
  3. Re-run ./deploy/deploy-apm-java-demo.sh

EOF
    exit 1
fi

ls -la "${DEST}"
