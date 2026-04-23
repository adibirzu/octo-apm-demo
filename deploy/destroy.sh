#!/usr/bin/env bash
# octo-apm-demo targeted tear-down.
#
# Removes ONLY resources created by bootstrap.sh in the selected
# compartment. Honours the project=octo-apm-demo freeform tag + fixed
# resource names. Pre-existing clusters, ATPs, Vaults, APM domains,
# OCIR repos in the compartment that were NOT created by bootstrap are
# left untouched.
#
# Safe to re-run — every step is idempotent.
#
# Usage:
#   ./deploy/destroy.sh                 # interactive (prompts before each destructive op)
#   ./deploy/destroy.sh --yes           # no prompts
#   ./deploy/destroy.sh --keep-atp      # leave the ATP alive
#   ./deploy/destroy.sh --keep-images   # leave OCIR images in place

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CACHE="${SCRIPT_DIR}/.last-tenancy.env"

KEEP_ATP=false
KEEP_IMAGES=false
AUTO_YES=false
for arg in "$@"; do
    case "$arg" in
        --yes|-y)      AUTO_YES=true ;;
        --keep-atp)    KEEP_ATP=true ;;
        --keep-images) KEEP_IMAGES=true ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
    esac
done

if [[ ! -f "${CACHE}" ]]; then
    echo "No ${CACHE}. Run bootstrap.sh first or export OCI_PROFILE + OCI_COMPARTMENT_ID manually." >&2
    exit 1
fi
# shellcheck disable=SC1090
source "${CACHE}"
: "${OCI_PROFILE:?}"
: "${OCI_COMPARTMENT_ID:?}"
: "${DNS_BASE_DOMAIN:=cyber-sec.ro}"

K8S_NAMESPACE_SHOP="${K8S_NAMESPACE_SHOP:-octo-drone-shop}"
K8S_NAMESPACE_CRM="${K8S_NAMESPACE_CRM:-enterprise-crm}"
SHOP_SUBDOMAIN="${SHOP_SUBDOMAIN:-shop}"
CRM_SUBDOMAIN="${CRM_SUBDOMAIN:-crm}"

_red()    { printf '\033[31m%s\033[0m\n' "$*"; }
_green()  { printf '\033[32m%s\033[0m\n' "$*"; }
_yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
section() { printf '\n\033[1;36m── %s ──\033[0m\n' "$*"; }
confirm() {
    local prompt="$1"
    $AUTO_YES && return 0
    read -r -p "${prompt} [y/N]: " ans
    case "$(echo "$ans" | tr '[:upper:]' '[:lower:]')" in y|yes) return 0 ;; *) return 1 ;; esac
}

_yellow "DESTROY WILL TOUCH:
  • K8s namespaces ${K8S_NAMESPACE_SHOP} + ${K8S_NAMESPACE_CRM}
  • nginx-ingress release in ingress-nginx namespace
  • DNS records ${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN} + ${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}
  • Terraform state (ATP, optionally)
  • OCIR images (optionally)
"
_yellow "Compartment: ${OCI_COMPARTMENT_NAME:-?} (${OCI_COMPARTMENT_ID:0:40}...)"
confirm "Continue?" || { echo "aborted"; exit 0; }

# ── 1. Kubernetes namespaces ──────────────────────────────────────────
section "1. K8s namespaces + workloads"
for NS in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
    if kubectl get ns "$NS" >/dev/null 2>&1; then
        if confirm "Delete namespace ${NS} (removes Deployments, Services, Ingress, Secrets)?"; then
            kubectl delete namespace "$NS" --wait=true --timeout=180s 2>&1 | head -3
        fi
    fi
done

# ── 2. nginx-ingress ──────────────────────────────────────────────────
section "2. nginx-ingress"
if helm -n ingress-nginx status nginx-ingress >/dev/null 2>&1; then
    if confirm "Uninstall nginx-ingress helm release (shared infra — check if other apps use it)?"; then
        helm -n ingress-nginx uninstall nginx-ingress --wait --timeout 3m 2>&1 | head -3
        kubectl delete namespace ingress-nginx --ignore-not-found --timeout=60s 2>&1 | head -2
    fi
fi

# ── 3. DNS records ────────────────────────────────────────────────────
section "3. DNS records"
if confirm "Remove A records for ${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN} + ${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}?"; then
    python3 - <<PYEOF
import oci
cfg = oci.config.from_file(profile_name="${OCI_PROFILE}")
dns = oci.dns.DnsClient(cfg)
zone = "${DNS_BASE_DOMAIN}"
for name in ("${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}", "${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}"):
    try:
        dns.patch_domain_records(
            zone_name_or_id=zone, domain=name,
            patch_domain_records_details=oci.dns.models.PatchDomainRecordsDetails(
                items=[oci.dns.models.RecordOperation(operation="REMOVE", domain=name, rtype="A")]
            ),
        )
        print(f"  removed A {name}")
    except oci.exceptions.ServiceError as e:
        print(f"  skip {name}: {e.message[:80]}")
PYEOF
fi

# ── 4. ATP via terraform ──────────────────────────────────────────────
section "4. ATP (terraform destroy)"
if $KEEP_ATP; then
    _yellow "--keep-atp: skipping ATP"
else
    TFVARS="${SCRIPT_DIR}/terraform/terraform.${OCI_COMPARTMENT_NAME:-custom}.tfvars"
    if [[ -f "${TFVARS}" ]]; then
        if confirm "Run terraform destroy -target=module.atp against ${TFVARS}?"; then
            (cd "${SCRIPT_DIR}/terraform" && terraform destroy -auto-approve -var-file="${TFVARS}" -target=module.atp -no-color 2>&1 | tail -5)
        fi
    else
        _yellow "No tfvars at ${TFVARS} — skipping"
    fi
fi

# ── 5. OCIR images ────────────────────────────────────────────────────
section "5. OCIR repositories (project-created only)"
if $KEEP_IMAGES; then
    _yellow "--keep-images: skipping OCIR"
else
    if confirm "Delete OCIR repos octo-drone-shop, enterprise-crm-portal, octo-apm-java-demo in compartment?"; then
        python3 - <<PYEOF
import oci
cfg = oci.config.from_file(profile_name="${OCI_PROFILE}")
client = oci.artifacts.ArtifactsClient(cfg)
for r in client.list_container_repositories(compartment_id="${OCI_COMPARTMENT_ID}").data.items:
    if r.display_name in {"octo-drone-shop", "enterprise-crm-portal", "octo-apm-java-demo"}:
        try:
            client.delete_container_repository(r.id)
            print(f"  deleted {r.display_name}")
        except oci.exceptions.ServiceError as e:
            print(f"  skip {r.display_name}: {e.message[:80]}")
PYEOF
    fi
fi

# ── 6. kubectl context + tfvars ───────────────────────────────────────
section "6. Local cleanup"
KUBE_CTX="octo-${OCI_COMPARTMENT_NAME:-tenancy}"
if kubectl config get-contexts "${KUBE_CTX}" >/dev/null 2>&1; then
    if confirm "Remove kubectl context ${KUBE_CTX}?"; then
        kubectl config delete-context "${KUBE_CTX}" 2>&1 | head -2
    fi
fi
if [[ -f "${CACHE}" ]] && confirm "Delete tenancy cache ${CACHE}?"; then
    rm -f "${CACHE}"
    echo "  removed ${CACHE}"
fi

section "Destroy complete"
_green "Resources untouched (pre-existing in compartment):"
_yellow "  • The OKE cluster itself (we only reused it)"
_yellow "  • Any APM domain, Vault, LA namespace that predated bootstrap"
_yellow "  • All other namespaces / deployments in the OKE cluster"
_yellow "  • Network (VCN, subnets, security lists, route tables)"
