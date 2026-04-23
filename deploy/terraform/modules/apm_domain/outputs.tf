###############################################################################
# APM Domain module outputs.
#
# Consumed by: deploy/oci/ensure_apm.sh (prints to stdout for env export),
# deploy/k8s/deployment.yaml (via secret injection), and app config.py
# (OCI_APM_ENDPOINT, OCI_APM_PUBLIC_DATAKEY, OCI_APM_PRIVATE_DATAKEY).
###############################################################################

output "apm_domain_id" {
  value       = oci_apm_apm_domain.this.id
  description = "OCID of the APM Domain."
}

output "apm_data_upload_endpoint" {
  value       = oci_apm_apm_domain.this.data_upload_endpoint
  description = "Trace/log data upload endpoint (set as OCI_APM_ENDPOINT)."
}

output "apm_public_datakey" {
  value       = try(data.oci_apm_data_keys.public.data_keys[0].value, "")
  description = "Public data key used by RUM browser SDK (set as OCI_APM_PUBLIC_DATAKEY)."
  sensitive   = true
}

output "apm_private_datakey" {
  value       = try(data.oci_apm_data_keys.private.data_keys[0].value, "")
  description = "Private data key used by OTel exporter (set as OCI_APM_PRIVATE_DATAKEY)."
  sensitive   = true
}

output "rum_web_application_id" {
  value       = ""
  description = "RUM web application OCID — returned by the OCI Console after manual registration (see main.tf note). Leave OCI_APM_WEB_APPLICATION empty for beacon-only use."
}

output "rum_endpoint" {
  # OCI RUM uses the same data-upload endpoint as APM but a different path;
  # the browser SDK composes the full URL from this base.
  value       = oci_apm_apm_domain.this.data_upload_endpoint
  description = "RUM data upload endpoint (set as OCI_APM_RUM_ENDPOINT)."
}
