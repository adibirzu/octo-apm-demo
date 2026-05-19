"""octo-stress-runner — FastAPI wrapper around k6 for the OKE stress demo.

See main.py for the HTTP control plane (POST /internal/run, POST /internal/clear,
GET /internal/state, GET /internal/healthz). All internal endpoints are gated by
the X-Internal-Service-Key header sourced from the OCTO_STRESS_RUNNER_INTERNAL_KEY
env var (k8s Secret octo-stress-runner-key in deployment.yaml).
"""

__all__ = ["main"]
