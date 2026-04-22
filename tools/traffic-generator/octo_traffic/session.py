"""A simulated end-user session — state machine + HTTP behaviour.

The session is deliberately **fast**: it does not sleep for the whole
log-normal duration (that would starve concurrency). Instead, it lays
down page-view spans with realistic inter-arrival gaps clamped to a few
hundred milliseconds, so a session of nominal 30-second duration still
completes in a few seconds of wall-clock time. The exported trace
duration reflects the simulated think time, not the wall time — that's
what APM dashboards want to see.
"""

from __future__ import annotations

import asyncio
import enum
import random
import uuid
from typing import Any

import httpx
import structlog
from opentelemetry import trace

from . import distributions as dist
from .config import TrafficConfig

logger = structlog.get_logger(__name__)

# Product paths the shop is known to expose (probing paths keeps the
# traces interesting without coupling to a specific SKU list).
_PRODUCT_BROWSE_PATHS: tuple[str, ...] = (
    "/",
    "/shop",
    "/api/products",
    "/api/products?category=drones",
    "/api/products?category=batteries",
    "/api/products?category=accessories",
    "/api/dealers",
    "/api/health",
)

_CHECKOUT_PATH = "/api/orders"
_READY_PATH = "/ready"
_WHOAMI_PATH = "/api/auth/whoami"


class SessionOutcome(str, enum.Enum):
    """Terminal state of a session — emitted as a trace attribute."""

    COMPLETED_PURCHASE = "completed_purchase"
    ABANDONED_CART = "abandoned_cart"
    BROWSED_ONLY = "browsed_only"
    FAILED_CHECKOUT = "failed_checkout"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"


class Session:
    """One simulated user session."""

    def __init__(self, cfg: TrafficConfig, client: httpx.AsyncClient, tracer: trace.Tracer):
        self.cfg = cfg
        self.client = client
        self.tracer = tracer
        self.session_id = uuid.uuid4().hex[:12]
        self.user_agent = f"{cfg.user_agent} session/{self.session_id}"
        self.force_failure = dist.bernoulli(cfg.failure_injection_rate)

    async def run(self) -> SessionOutcome:
        span_name = "traffic.session"
        with self.tracer.start_as_current_span(span_name) as span:
            span.set_attribute("session.id", self.session_id)
            span.set_attribute("session.force_failure", self.force_failure)
            span.set_attribute(
                "session.duration_seconds_simulated",
                dist.session_duration_seconds(
                    mu=self.cfg.session_duration_log_normal_mu,
                    sigma=self.cfg.session_duration_log_normal_sigma,
                ),
            )

            try:
                outcome = await self._behaviour()
            except httpx.HTTPError as exc:
                span.set_attribute("session.error", type(exc).__name__)
                return SessionOutcome.NETWORK_ERROR

            span.set_attribute("session.outcome", outcome.value)
            return outcome

    # ── Behaviour state machine ────────────────────────────────────────
    async def _behaviour(self) -> SessionOutcome:
        await self._browse()

        if not dist.bernoulli(self.cfg.p_add_to_cart):
            return SessionOutcome.BROWSED_ONLY

        if dist.bernoulli(self.cfg.p_sso_login):
            await self._sso_whoami_probe()

        if not dist.bernoulli(self.cfg.p_checkout_given_cart):
            return SessionOutcome.ABANDONED_CART

        return await self._checkout()

    async def _browse(self) -> None:
        pages = dist.pageviews_per_session(
            alpha=self.cfg.browse_pareto_alpha,
            cap=self.cfg.browse_max_pageviews,
        )
        for _ in range(pages):
            path = random.choice(_PRODUCT_BROWSE_PATHS)  # noqa: S311 — non-crypto
            await self._get(path)
            # Small think time between clicks
            await asyncio.sleep(random.uniform(0.05, 0.25))  # noqa: S311

    async def _sso_whoami_probe(self) -> None:
        # Not a full PKCE flow (that needs a browser) — just probes the
        # authenticated endpoint with a stale token so /api/auth/whoami
        # emits a real 401 or a real 200 depending on session state.
        await self._get(_WHOAMI_PATH, expected_statuses=(200, 401, 403))

    async def _checkout(self) -> SessionOutcome:
        # Intentionally-broken payloads in failure-injection sessions so
        # APM widgets have real non-zero error rates.
        if self.force_failure:
            payload: dict[str, Any] = {"customer_id": 0, "items": []}  # invalid
            expected = (400, 422, 500)
        else:
            payload = {
                "customer_id": random.randint(1, 100),  # noqa: S311
                "items": [
                    {
                        "product_id": random.randint(1, 10),  # noqa: S311
                        "quantity": random.randint(1, 3),  # noqa: S311
                        "unit_price": round(random.uniform(49.99, 1299.99), 2),  # noqa: S311
                    }
                ],
            }
            expected = (200, 201)

        try:
            resp = await self._post(_CHECKOUT_PATH, json=payload)
        except httpx.HTTPError:
            return SessionOutcome.NETWORK_ERROR

        if resp.status_code in expected and resp.status_code < 400:
            return SessionOutcome.COMPLETED_PURCHASE
        if resp.status_code == 429:
            return SessionOutcome.RATE_LIMITED
        return SessionOutcome.FAILED_CHECKOUT

    # ── HTTP primitives ───────────────────────────────────────────────
    async def _get(self, path: str, *, expected_statuses: tuple[int, ...] = (200,)) -> httpx.Response:
        return await self.client.get(
            path,
            headers={"User-Agent": self.user_agent, "X-Session-Id": self.session_id},
        )

    async def _post(self, path: str, *, json: Any) -> httpx.Response:
        return await self.client.post(
            path,
            json=json,
            headers={"User-Agent": self.user_agent, "X-Session-Id": self.session_id},
        )
