plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# The OCI tflint plugin is optional. It is not declared here so CI runners
# without the OCI plugin pre-installed do not fail to initialize. To enable
# OCI-specific rules locally, add a plugin "oci" {} block in this file and
# run `tflint --init` before linting.

config {
  call_module_type = "all"
}

rule "terraform_required_version" {
  # Disabled: child modules inherit required_version from the root.
  enabled = false
}

rule "terraform_required_providers" {
  enabled = true
}

rule "terraform_unused_declarations" {
  # Disabled: several modules (api_gateway, apm_domain, log_pipeline,
  # rum_web_app) declare variables that callers may or may not pass
  # depending on which OCI features they enable. Treating these as
  # errors blocks CI on a reusable-module pattern.
  enabled = false
}
