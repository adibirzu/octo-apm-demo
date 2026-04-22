"""CLI entry point — invoked as ``octo-traffic`` after ``pip install .``.

Examples:

  # Continuous (Kubernetes Deployment mode)
  octo-traffic

  # 60-second burst (Kubernetes Job mode)
  OCTO_TRAFFIC_RUN_DURATION_SECONDS=60 octo-traffic

  # Point at a different environment
  OCTO_TRAFFIC_SHOP_BASE_URL=https://staging-drone.octodemo.cloud \\
    OCTO_TRAFFIC_TARGET_RPS=10 octo-traffic
"""

from __future__ import annotations

import asyncio
import logging
import sys

import structlog
from rich.console import Console
from rich.table import Table

from .config import TrafficConfig
from .population import Population


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s", stream=sys.stderr)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


def _banner(cfg: TrafficConfig) -> None:
    t = Table(title="octo-traffic-generator — starting", show_header=False)
    t.add_column("Key", style="cyan")
    t.add_column("Value")
    t.add_row("Shop target", cfg.shop_base_url)
    t.add_row("CRM target", cfg.crm_base_url)
    t.add_row("Target RPS", f"{cfg.target_rps:.2f}")
    t.add_row("Concurrent cap", str(cfg.concurrent_session_limit))
    t.add_row("Failure injection", f"{cfg.failure_injection_rate:.0%}")
    t.add_row("Duration", "forever" if cfg.run_duration_seconds == 0 else f"{cfg.run_duration_seconds}s")
    t.add_row("OTLP endpoint", cfg.otel_exporter_otlp_endpoint or "(none — local only)")
    Console().print(t)


def main() -> int:
    cfg = TrafficConfig()
    _configure_logging(cfg.log_level)
    _banner(cfg)

    population = Population(cfg)
    try:
        asyncio.run(population.run())
    except KeyboardInterrupt:
        print("interrupted — exporting summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
