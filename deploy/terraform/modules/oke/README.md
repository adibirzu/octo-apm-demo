# OKE module

Provisions a VCN-native OKE cluster sized for octo-apm-demo when the
tenancy does not already have one. Opt-in via `create_oke = true` in
the root `terraform.tfvars`.

## What it creates

| Resource | Notes |
|---|---|
| VCN `10.0.0.0/16` | Configurable via `vcn_cidr`. |
| Internet Gateway | Public egress for k8s API + LB subnets. |
| NAT Gateway | Outbound egress for private worker subnet. |
| Service Gateway | Private connectivity to OCI services (OCIR, ATP wallet, object storage). |
| Subnets | `k8s-api` (public), `workers` (private), `lb` (public), `pods` (private, /18). |
| OKE cluster | Enhanced, VCN-native pod networking. |
| Node pool | Default 3 × VM.Standard.E5.Flex · 2 OCPU · 16 GiB mem · 93 GiB boot volume. |

**Why the bigger boot volume**: KB-OCTO-06 — the OKE default of 37 GiB
runs out under image cache + container logs + overlay FS, and the
kubelet starts evicting pods. 93 GiB is the smallest size that sustains
our demo workload.

## Inputs you must supply

```hcl
compartment_id            = "ocid1.compartment.oc1..xxx"
availability_domain_names = ["FHlk:EU-FRANKFURT-1-AD-1", "FHlk:EU-FRANKFURT-1-AD-2", "FHlk:EU-FRANKFURT-1-AD-3"]
node_image_id             = "ocid1.image.oc1.eu-frankfurt-1.xxx"   # OKE-managed image
```

Get the managed node image OCID matching your k8s version:

```bash
oci ce node-pool-options get --node-pool-option-id all --profile DEFAULT \
    | jq '.data.sources[] | select(."source-name" | test("OKE.*Oracle-Linux-8.*")) | {image_id: ."image-id", source_name: ."source-name"}' \
    | head -30
```

## Outputs consumed downstream

| Output | Downstream use |
|---|---|
| `cluster_id` | `oci ce cluster create-kubeconfig --cluster-id ...` |
| `lb_subnet_id` | `OCI_LB_SUBNET_OCID` env var on shop + crm deployments. |
| `vcn_id` | Peering, additional subnets, network policy debugging. |

## Post-apply steps

```bash
# 1. Kubeconfig
oci ce cluster create-kubeconfig \
    --cluster-id $(terraform output -raw cluster_id) \
    --file ~/.kube/config \
    --region $TF_VAR_region \
    --token-version 2.0.0 \
    --kube-endpoint PUBLIC_ENDPOINT \
    --profile DEFAULT

kubectl config rename-context $(kubectl config current-context) oci4cca-oke

# 2. Namespaces + imagePullSecret (if not using instance-principal OCIR pull)
kubectl create namespace octo-drone-shop
kubectl create namespace enterprise-crm
```
