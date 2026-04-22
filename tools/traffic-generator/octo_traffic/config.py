"""Runtime configuration for the traffic generator.

Lives in env vars + optional --config yaml so the same binary can run
as a local script, a K8s Deployment (continuous), or a K8s Job (burst).
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrafficConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OCTO_TRAFFIC_", env_file=".env")

    # ── Targets ──
    shop_base_url: str = Field(
        default="https://drone.octodemo.cloud",
        description="Drone Shop public URL.",
    )
    crm_base_url: str = Field(
        default="https://backend.octodemo.cloud",
        description="Enterprise CRM public URL (for partner-mode simulations).",
    )
    verify_tls: bool = True

    # ── Load shape ──
    target_rps: float = Field(
        default=2.0,
        description="Approximate new sessions per second. Realistic sizing: "
        "2-5 for demo, 20-50 for dev, 200+ for pre-prod.",
    )
    concurrent_session_limit: int = Field(
        default=50,
        description="Hard cap on in-flight sessions — protects the generator "
        "itself from runaway concurrency.",
    )
    burst_multiplier: float = Field(
        default=1.0,
        description="Multiplier applied to target_rps during random burst "
        "windows (simulates flash sales). 1.0 = no bursts.",
    )

    # ── Session behavior distributions ──
    # Pareto α = tails the distribution: lower α = heavier tail = a few
    # users browse a lot of products.
    browse_pareto_alpha: float = 1.7
    browse_max_pageviews: int = 30

    session_duration_log_normal_mu: float = 5.0    # mean ln(seconds)
    session_duration_log_normal_sigma: float = 0.8

    # Funnel conversion probabilities
    p_add_to_cart: float = 0.55
    p_checkout_given_cart: float = 0.30
    p_sso_login: float = 0.25
    p_partner_api_hit: float = 0.05  # small amount of /api/v1/partner/* traffic

    # ── Failure injection ──
    failure_injection_rate: float = Field(
        default=0.05,
        description="Fraction of sessions that will intentionally tickle a "
        "failure path (bad product id, quantity 0, abandoned cart, 429, "
        "network retry). Keeps APM error widgets non-empty in demos.",
    )
    chaos_mode: bool = False  # when True, applies CRM /admin/chaos toggles

    # ── OTel export (OTLP HTTP to OCI APM) ──
    otel_service_name: str = "octo-traffic-generator"
    otel_exporter_otlp_endpoint: str = ""      # empty = no trace export
    otel_exporter_otlp_headers: str = ""       # "api-key=...,k2=v2"
    otel_resource_attributes: str = "service.namespace=octo,deployment.environment=production"

    # ── Runtime ──
    run_duration_seconds: int = Field(
        default=0,
        description="0 = run forever (K8s Deployment mode). >0 = exit after N seconds (K8s Job/one-shot).",
    )
    log_level: str = "INFO"
    user_agent: str = "octo-traffic-sim/1.0 (+https://github.com/adibirzu/octo-apm-demo)"
    seed: int = 0  # 0 = non-deterministic; any other value = reproducible run

    @field_validator("target_rps", "concurrent_session_limit")
    @classmethod
    def _positive(cls, v: float | int) -> float | int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    @field_validator("p_add_to_cart", "p_checkout_given_cart", "p_sso_login", "p_partner_api_hit", "failure_injection_rate")
    @classmethod
    def _probability(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be in [0.0, 1.0]")
        return v
