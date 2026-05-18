# Phase 4: Deployment Parity and Release Gates - Patterns

## Deployment Contract Pattern

Every production-capable runtime path must expose:

- `SERVICE_NAMESPACE=octo`
- service instance identity (`SERVICE_INSTANCE_ID` or pod-derived equivalent)
- `DEMO_STACK_NAME=octo-apm-demo` for OKE and compatible stack tags for
  Compute
- `OCI_MONITORING_NAMESPACE=octo_apm_demo`
- APM endpoint/private key inputs
- OCI Logging group/log inputs
- `OTEL_RESOURCE_ATTRIBUTES` with service namespace, environment, OCI demo
  stack, and Kubernetes identity where relevant

## Payment Gateway Pattern

Deployment paths that can serve checkout must include the Java payment gateway
surface or a documented equivalent:

- Shop points to `JAVA_APM_SERVICE_URL`.
- Shop emits `JAVA_APM_SERVICE_NAME`.
- Payment remains simulated with `PAYMENT_PROVIDER=simulated` and
  `PAYMENT_GATEWAY_SIMULATION_ENABLED=true`.
- Apple Pay, Google Pay, Visa, and Mastercard remain token-safe demo flows.

## Release Gate Pattern

Before live promotion:

1. Run local source gates: pytest, Helm render/lint, deploy verifier, and
   docs build.
2. Run non-destructive OKE gates with `SERVER_DRY_RUN=true` and
   `APPLY=false`.
3. Validate VM and OKE directly before public LB round-robin.
4. Promote with explicit LB helper flags only during an approved window.
5. Keep `--rollback-active-vm` ready for VM-only rollback.

## Safety Pattern

Scripts and docs must not contain hardcoded secrets, OCIDs, private IPs, wallet
paths, or operator-only values. Live shared emdemo resources are changed only
by explicit operator commands.
