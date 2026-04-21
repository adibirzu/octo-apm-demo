# Remote state configuration for OCTO Drone Shop terraform.
#
# Local state is dangerous for multi-operator + CI deployments: every
# terraform apply would race and corrupt the tfstate. For shared
# environments, use an OCI Object Storage bucket with versioning enabled.
#
# Initialize (once per tenancy):
#
#   terraform init \
#     -backend-config="bucket=<bucket-name>" \
#     -backend-config="namespace=<object-storage-namespace>" \
#     -backend-config="key=octo-drone-shop/<env>.tfstate" \
#     -backend-config="region=<region-slug>" \
#     -backend-config="auth=InstancePrincipal"
#
# Uncomment the block below to opt into remote state. Kept commented so
# `terraform init` in a fresh clone does not require pre-provisioned
# object storage.

# terraform {
#   backend "oci" {
#     # values supplied via -backend-config on init
#   }
# }
