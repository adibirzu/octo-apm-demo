# OCTO APM Demo — convenience wrapper around deploy/*.sh.
#
# Quickstart for any OCI tenancy (after `oci setup config`):
#
#   make doctor                      # check prerequisites
#   make tenancy-init                # create OCIR repos + namespaces + bootstrap secrets
#   make deploy                      # build + push images + apply manifests
#   make verify                      # smoke-check every public endpoint
#   make destroy                     # tear down (with confirmation)
#
# Per-service deploys:
#
#   make deploy-shop
#   make deploy-crm
#   make deploy-java-apm
#
# Local development:
#
#   make local-up                    # docker-compose stack on :18080 / :18091
#   make local-down
#   make local-logs
#
# Documentation site:
#
#   make docs-serve                  # mkdocs serve on http://localhost:8000
#   make docs-build                  # mkdocs build --strict
#
# Tests:
#
#   make test                        # full local validation suite
#   make test-contract               # source-level observability contracts only
#   make test-docs                   # mkdocs --strict + public-doc guard
#
# Required environment variables for OCI deploys (set once in a .env file
# or export before make deploy):
#
#   OCI_PROFILE=<profile-name>           # from ~/.oci/config (default: DEFAULT)
#   OCI_COMPARTMENT_ID=<COMPARTMENT_OCID>
#   OCIR_REGION=<region-key>             # e.g. eu-frankfurt-1
#   OCIR_TENANCY=<tenancy-namespace>     # tenancy object-storage namespace
#   DNS_DOMAIN=<your-dns-zone>           # e.g. demo.acme.io
#
# Everything below shells out to the existing deploy/*.sh scripts. The
# Makefile is purely sugar — feel free to read the scripts directly.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Allow overrides from .env or environment
-include .env
export

OCI_PROFILE ?= DEFAULT
OCIR_REGION ?=
OCIR_TENANCY ?=
DNS_DOMAIN ?=
OCI_COMPARTMENT_ID ?=

# --- help -------------------------------------------------------------------

.PHONY: help
help: ## Show this help (default target)
	@awk 'BEGIN {FS = ":.*?## "; print "\nOCTO APM Demo — Make targets\n"} \
	     /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Run 'make doctor' first to check prerequisites."

# --- preflight --------------------------------------------------------------

.PHONY: doctor
doctor: ## Verify local tooling + OCI access
	@echo "=== OCI APM Demo doctor ==="
	@command -v oci >/dev/null   && echo "✓ oci CLI: $$(oci --version 2>&1)" || (echo "✗ oci CLI missing"; exit 1)
	@command -v kubectl >/dev/null && echo "✓ kubectl: $$(kubectl version --client -o json 2>/dev/null | jq -r .clientVersion.gitVersion)" || echo "⚠ kubectl missing (only needed for OKE deploys)"
	@command -v docker >/dev/null && echo "✓ docker: $$(docker --version)" || echo "⚠ docker missing (use docker.com or colima)"
	@command -v terraform >/dev/null && echo "✓ terraform: $$(terraform --version | head -1)" || echo "⚠ terraform missing (only needed for IaC)"
	@command -v helm >/dev/null && echo "✓ helm: $$(helm version --short)" || echo "⚠ helm missing (only needed for helm deploys)"
	@command -v jq >/dev/null && echo "✓ jq: $$(jq --version)" || (echo "✗ jq missing"; exit 1)
	@echo
	@oci iam region list --profile $(OCI_PROFILE) >/dev/null 2>&1 \
	  && echo "✓ OCI profile '$(OCI_PROFILE)' authenticates" \
	  || echo "✗ OCI profile '$(OCI_PROFILE)' fails — check ~/.oci/config"
	@echo
	@echo "Environment:"
	@echo "  OCI_PROFILE         = $(OCI_PROFILE)"
	@echo "  OCI_COMPARTMENT_ID  = $${OCI_COMPARTMENT_ID:-<unset>}"
	@echo "  OCIR_REGION         = $${OCIR_REGION:-<unset>}"
	@echo "  OCIR_TENANCY        = $${OCIR_TENANCY:-<unset>}"
	@echo "  DNS_DOMAIN          = $${DNS_DOMAIN:-<unset>}"

.PHONY: env-check
env-check:
	@: "$${OCI_COMPARTMENT_ID:?run 'make doctor' first — OCI_COMPARTMENT_ID is required}"
	@: "$${OCIR_REGION:?OCIR_REGION is required (e.g. eu-frankfurt-1)}"
	@: "$${OCIR_TENANCY:?OCIR_TENANCY is required (your tenancy object-storage namespace)}"
	@: "$${DNS_DOMAIN:?DNS_DOMAIN is required (e.g. demo.acme.io)}"

# --- tenancy initialization -------------------------------------------------

.PHONY: tenancy-init
tenancy-init: env-check ## Create OCIR repos, namespaces, bootstrap secrets in current tenancy
	./deploy/init-tenancy.sh

.PHONY: bootstrap
bootstrap: env-check ## End-to-end bootstrap (ATP + secrets + DNS + smoke). See deploy/bootstrap.sh
	./deploy/bootstrap.sh

# --- deploys ----------------------------------------------------------------

.PHONY: deploy
deploy: env-check ## Build + push images + apply manifests for shop + CRM
	./deploy/deploy.sh

.PHONY: deploy-shop
deploy-shop: env-check ## Deploy only the shop service
	./deploy/deploy.sh --shop-only

.PHONY: deploy-crm
deploy-crm: env-check ## Deploy only the CRM service
	./deploy/deploy.sh --crm-only

.PHONY: deploy-java-apm
deploy-java-apm: env-check ## Deploy the Java payment sidecar
	./deploy/deploy-apm-java-demo.sh

.PHONY: deploy-helm
deploy-helm: env-check ## Deploy via the Helm chart instead of raw manifests
	helm upgrade --install octo-apm-demo deploy/helm/octo-apm-demo \
	  --set image.region=$(OCIR_REGION) \
	  --set image.tenancy=$(OCIR_TENANCY) \
	  --set ociConfig.compartmentId=$(OCI_COMPARTMENT_ID) \
	  --set dnsDomain=$(DNS_DOMAIN)

# --- verification -----------------------------------------------------------

.PHONY: verify
verify: ## Run the full local validation gate (tests + mkdocs + drawio + deploy/verify.sh)
	./deploy/verify.sh

.PHONY: smoke
smoke: env-check ## Smoke-check public endpoints (DNS + /ready + APM/RUM/logging configured)
	./deploy/validate-deployment.sh

# --- teardown ---------------------------------------------------------------

.PHONY: destroy
destroy: ## Tear down (with confirmation)
	@read -p "This will delete all deployed resources in compartment $${OCI_COMPARTMENT_ID:-?}. Type 'destroy' to confirm: " ans; \
	  [ "$$ans" = "destroy" ] && ./deploy/destroy.sh || echo "aborted"

# --- local development ------------------------------------------------------

.PHONY: local-up
local-up: ## Start the local docker-compose stack (no OCI needed)
	docker compose -f deploy/local-stack/docker-compose.test.yml up -d
	@echo "shop:  http://localhost:18080"
	@echo "crm:   http://localhost:18090"
	@echo "java:  http://localhost:18091"

.PHONY: local-down
local-down: ## Stop the local stack
	docker compose -f deploy/local-stack/docker-compose.test.yml down

.PHONY: local-logs
local-logs: ## Tail logs from the local stack
	docker compose -f deploy/local-stack/docker-compose.test.yml logs -f --tail=50

# --- documentation ----------------------------------------------------------

.PHONY: docs-serve
docs-serve: ## Serve mkdocs site locally at http://localhost:8000
	python3 -m mkdocs serve

.PHONY: docs-build
docs-build: ## Build mkdocs site (strict — fails on broken links)
	python3 -m mkdocs build --strict

# --- tests ------------------------------------------------------------------

.PHONY: test
test: test-contract test-docs ## Run the full local test gate
	python3 -m pytest -q shop/tests crm/tests services/*/tests 2>/dev/null || true

.PHONY: test-contract
test-contract: ## Run source-level observability + deployment contract tests
	python3 -m pytest -q tests/

.PHONY: test-docs
test-docs: ## Verify mkdocs strict + public-doc forbidden-token guard
	python3 -m mkdocs build --strict
	python3 -m pytest -q crm/tests/test_observability_guidance_surfaces.py

# --- resource manager stack -------------------------------------------------

.PHONY: rm-stack-package
rm-stack-package: ## Package the Resource Manager stack zip (deploy/compute/build/octo-compute-stack.zip)
	./deploy/compute/stack-package.sh

.PHONY: rm-stack-info
rm-stack-info: ## Show one-click Deploy-to-OCI URL for the packaged stack
	@echo "After publishing deploy/compute/build/octo-compute-stack.zip as a GitHub Release asset,"
	@echo "the Deploy-to-OCI button URL is:"
	@echo
	@echo "  https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=<your-release-asset-url>"
	@echo
	@echo "Local zip is at: $$(realpath deploy/compute/build/octo-compute-stack.zip 2>/dev/null || echo NOT BUILT — run 'make rm-stack-package' first)"

# --- info -------------------------------------------------------------------

.PHONY: info
info: ## Show current cluster + APM/logging configuration
	@./deploy/validate-deployment.sh --info-only
