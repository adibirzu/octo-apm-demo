###############################################################################
# OCI Kubernetes Engine (OKE) — VCN-native "enhanced" cluster + managed
# node pool sized for the octo-apm-demo workload.
#
# Provisions (when create_oke = true in the root):
#   - VCN + 3 subnets (k8s-api, worker-nodes, service-loadbalancer)
#   - Internet Gateway + NAT Gateway + Service Gateway
#   - Route tables + security lists for each subnet
#   - OKE cluster (enhanced, VCN-native pod networking / OCI_VCN_IP_NATIVE)
#   - One node pool: VM.Standard.E5.Flex, 2 OCPUs, 16 GiB mem, 3 nodes,
#     boot volume 93 GB (KB-OCTO-06 — 37 GB default hits disk pressure)
#
# This module is OPT-IN. When the tenancy already has an OKE cluster,
# pass create_oke = false and supply `existing_cluster_id` to the root.
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

variable "compartment_id" {
  type = string
}

variable "cluster_name" {
  type    = string
  default = "octo-apm-demo-oke"
}

variable "kubernetes_version" {
  type    = string
  default = "v1.31.1"
  validation {
    condition     = can(regex("^v1\\.(2[89]|3[0-4])\\.", var.kubernetes_version))
    error_message = "kubernetes_version must be a supported OKE version (v1.28–v1.34)."
  }
}

variable "vcn_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "node_pool_size" {
  type    = number
  default = 3
  validation {
    condition     = var.node_pool_size >= 1 && var.node_pool_size <= 12
    error_message = "node_pool_size must be 1-12."
  }
}

variable "node_shape" {
  type    = string
  default = "VM.Standard.E5.Flex"
}

variable "node_ocpus" {
  type    = number
  default = 2
}

variable "node_memory_gbs" {
  type    = number
  default = 16
}

variable "node_boot_volume_gbs" {
  type    = number
  default = 93
  validation {
    condition     = var.node_boot_volume_gbs >= 50
    error_message = "node_boot_volume_gbs must be >= 50 GiB. Default 37 GiB hits disk-pressure evictions (KB-OCTO-06)."
  }
}

variable "node_image_id" {
  type        = string
  description = "OKE-managed node image OCID (match kubernetes_version). `oci ce node-pool-options get --node-pool-option-id all` → sources."
}

variable "availability_domain_names" {
  type        = list(string)
  description = "Names of ADs to spread nodes across. E.g. [\"AD-1\", \"AD-2\", \"AD-3\"] or [\"FHlk:EU-FRANKFURT-1-AD-1\", ...]"
  validation {
    condition     = length(var.availability_domain_names) >= 1
    error_message = "Provide at least one AD name."
  }
}

# ────────────────────────────────────────────────────────────────────────────
# Network
# ────────────────────────────────────────────────────────────────────────────

resource "oci_core_vcn" "this" {
  compartment_id = var.compartment_id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.cluster_name}-vcn"
  dns_label      = substr(replace(var.cluster_name, "-", ""), 0, 15)

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

resource "oci_core_internet_gateway" "this" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-igw"
  enabled        = true
}

resource "oci_core_nat_gateway" "this" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-nat"
}

data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

resource "oci_core_service_gateway" "this" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-sgw"
  services {
    service_id = data.oci_core_services.all.services[0].id
  }
}

# ── Public route table (for k8s API + LoadBalancer subnets) ─────────
resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-rt-public"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.this.id
  }
}

# ── Private route table (for worker subnet — NAT + service GW only) ─
resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-rt-private"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.this.id
  }
  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.this.id
  }
}

# ── Subnets ─────────────────────────────────────────────────────────
resource "oci_core_subnet" "k8s_api" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 0) # 10.0.0.0/24
  display_name               = "${var.cluster_name}-k8s-api"
  dns_label                  = "api"
  route_table_id             = oci_core_route_table.public.id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "workers" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 1) # 10.0.1.0/24
  display_name               = "${var.cluster_name}-workers"
  dns_label                  = "workers"
  route_table_id             = oci_core_route_table.private.id
  prohibit_public_ip_on_vnic = true
}

resource "oci_core_subnet" "load_balancers" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 2) # 10.0.2.0/24
  display_name               = "${var.cluster_name}-lb"
  dns_label                  = "lb"
  route_table_id             = oci_core_route_table.public.id
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "pods" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 6, 1) # 10.0.64.0/18 — big for pod IPs
  display_name               = "${var.cluster_name}-pods"
  dns_label                  = "pods"
  route_table_id             = oci_core_route_table.private.id
  prohibit_public_ip_on_vnic = true
}

# ────────────────────────────────────────────────────────────────────────────
# OKE cluster (enhanced, VCN-native pod networking)
# ────────────────────────────────────────────────────────────────────────────

resource "oci_containerengine_cluster" "this" {
  compartment_id     = var.compartment_id
  name               = var.cluster_name
  vcn_id             = oci_core_vcn.this.id
  kubernetes_version = var.kubernetes_version
  type               = "ENHANCED_CLUSTER"

  endpoint_config {
    subnet_id            = oci_core_subnet.k8s_api.id
    is_public_ip_enabled = true
  }

  cluster_pod_network_options {
    cni_type = "OCI_VCN_IP_NATIVE"
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.load_balancers.id]
  }

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

resource "oci_containerengine_node_pool" "this" {
  cluster_id         = oci_containerengine_cluster.this.id
  compartment_id     = var.compartment_id
  name               = "${var.cluster_name}-pool"
  kubernetes_version = var.kubernetes_version
  node_shape         = var.node_shape

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gbs
  }

  node_source_details {
    image_id                = var.node_image_id
    source_type             = "IMAGE"
    boot_volume_size_in_gbs = var.node_boot_volume_gbs
  }

  node_config_details {
    size = var.node_pool_size
    dynamic "placement_configs" {
      for_each = var.availability_domain_names
      content {
        availability_domain = placement_configs.value
        subnet_id           = oci_core_subnet.workers.id
      }
    }
    node_pool_pod_network_option_details {
      cni_type       = "OCI_VCN_IP_NATIVE"
      pod_subnet_ids = [oci_core_subnet.pods.id]
    }
  }

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

output "cluster_id" {
  value = oci_containerengine_cluster.this.id
}

output "cluster_name" {
  value = oci_containerengine_cluster.this.name
}

output "vcn_id" {
  value = oci_core_vcn.this.id
}

output "lb_subnet_id" {
  value       = oci_core_subnet.load_balancers.id
  description = "Use for OCI_LB_SUBNET_OCID in deploy/k8s manifests."
}

output "kubeconfig_hint" {
  value = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.this.id} --file $HOME/.kube/config --region <region> --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT"
}
