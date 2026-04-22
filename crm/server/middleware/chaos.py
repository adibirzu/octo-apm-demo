"""Chaos engineering middleware — simulates infrastructure issues on demand."""

import asyncio
import random
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from server.config import cfg
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

# Accumulator for memory leak simulation
_leak_store: list[bytes] = []


class ChaosMiddleware(BaseHTTPMiddleware):
    """Inject failures based on SIMULATE_* environment flags."""

    async def dispatch(self, request: Request, call_next) -> Response:
        tracer = get_tracer()

        # CPU spike simulation
        if cfg.simulate_cpu_spike and random.random() < 0.3:
            with tracer.start_as_current_span("chaos.cpu_spike") as span:
                span.set_attribute("chaos.type", "cpu_spike")
                end = time.time() + 0.5
                while time.time() < end:
                    _ = sum(i * i for i in range(10000))
                push_log("WARNING", "Chaos: CPU spike injected", **{
                    "chaos.type": "cpu_spike",
                    "http.url.path": request.url.path,
                })

        # Memory leak simulation
        if cfg.simulate_memory_leak:
            with tracer.start_as_current_span("chaos.memory_leak") as span:
                chunk = bytes(1024 * 1024)  # 1 MB
                _leak_store.append(chunk)
                span.set_attribute("chaos.type", "memory_leak")
                span.set_attribute("chaos.leaked_mb", len(_leak_store))
                push_log("WARNING", "Chaos: memory leak injected", **{
                    "chaos.type": "memory_leak",
                    "chaos.total_leaked_mb": len(_leak_store),
                })

        # Slow query simulation (adds latency before DB-heavy routes)
        if cfg.simulate_slow_queries and request.url.path.startswith("/api/"):
            with tracer.start_as_current_span("chaos.slow_query") as span:
                delay = random.uniform(1.0, 5.0)
                span.set_attribute("chaos.type", "slow_query")
                span.set_attribute("chaos.delay_seconds", round(delay, 2))
                await asyncio.sleep(delay)

        # Error rate injection (configurable via /api/simulate/configure)
        # Skip simulation endpoints so the reset/configure APIs themselves still work.
        from server.modules.simulation import get_sim_state
        sim = get_sim_state()
        error_rate = sim.get("error_rate", 0.0)
        if error_rate > 0 and not request.url.path.startswith("/api/simulate"):
            if random.random() < error_rate:
                with tracer.start_as_current_span("chaos.error_rate") as span:
                    span.set_attribute("chaos.type", "error_rate")
                    span.set_attribute("chaos.error_rate", error_rate)
                    span.set_attribute("otel.status_code", "ERROR")
                    push_log("ERROR", "Chaos: simulated error (error_rate injection)", **{
                        "chaos.type": "error_rate",
                        "chaos.error_rate": error_rate,
                        "http.url.path": request.url.path,
                    })
                    return JSONResponse(
                        {"error": "Chaos: simulated error burst", "chaos": True},
                        status_code=500,
                    )

        return await call_next(request)
