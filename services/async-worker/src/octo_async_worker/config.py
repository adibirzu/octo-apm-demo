"""Runtime config. Env-driven so the same binary runs as K8s
Deployment (continuous) or one-shot Job (`--run-once`)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OCTO_WORKER_", env_file=".env")

    # ── Redis ──
    redis_url: str = Field(default="redis://cache.octo-cache.svc.cluster.local:6379")

    # ── Consumer group semantics ──
    consumer_group: str = Field(default="octo-async-worker")
    consumer_name: str = Field(
        default="",
        description="Unique consumer name (default: $HOSTNAME). Two pods with the "
        "same name will compete for the same messages.",
    )
    streams: list[str] = Field(
        default_factory=lambda: ["octo.orders.to-sync"],
        description="Streams to consume.",
    )
    block_ms: int = Field(default=5_000, ge=100, le=60_000)
    count_per_poll: int = Field(default=16, ge=1, le=1000)

    # ── Retry policy ──
    max_delivery_attempts: int = Field(default=5, ge=1, le=20)
    dlq_stream_suffix: str = Field(default=".dlq")
    retry_backoff_base_ms: int = Field(default=500, ge=50)
    retry_backoff_max_ms: int = Field(default=30_000, ge=1000)

    # ── Downstream targets ──
    crm_base_url: str = Field(default="https://backend.octodemo.cloud")
    shop_base_url: str = Field(default="https://drone.octodemo.cloud")
    internal_service_key: str = Field(default="")

    # ── Observability ──
    service_name: str = Field(default="octo-async-worker")
    otel_exporter_otlp_endpoint: str = Field(default="")
    log_level: str = Field(default="INFO")

    # ── Runtime ──
    run_once: bool = Field(
        default=False,
        description="If true, drain pending messages once + exit (K8s Job mode).",
    )
