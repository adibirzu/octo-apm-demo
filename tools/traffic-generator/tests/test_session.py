"""Session-level tests — patches httpx.AsyncClient so we can assert
the state machine transitions without a reachable shop.

Uses ``respx`` to fake HTTP responses deterministically.
"""

from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient, Response

from octo_traffic import distributions as dist
from octo_traffic.config import TrafficConfig
from octo_traffic.session import Session, SessionOutcome
from octo_traffic.telemetry import init_tracing


def _cfg(**overrides) -> TrafficConfig:
    return TrafficConfig(
        shop_base_url="https://shop.test.invalid",
        target_rps=1.0,
        concurrent_session_limit=1,
        otel_exporter_otlp_endpoint="",  # no real export
        run_duration_seconds=1,
        seed=42,
        **overrides,
    )


@pytest.fixture
def tracer():
    return init_tracing(_cfg())


@respx.mock
async def test_browse_only_session_completes_without_checkout(tracer) -> None:
    dist.set_seed(100)
    cfg = _cfg(p_add_to_cart=0.0, failure_injection_rate=0.0)

    respx.get(url__regex=r"^https://shop\.test\.invalid/.*").mock(
        return_value=Response(200, json={"ok": True})
    )

    async with AsyncClient(base_url=cfg.shop_base_url) as client:
        session = Session(cfg, client, tracer)
        outcome = await session.run()

    assert outcome == SessionOutcome.BROWSED_ONLY


@respx.mock
async def test_successful_checkout(tracer) -> None:
    dist.set_seed(200)
    cfg = _cfg(p_add_to_cart=1.0, p_checkout_given_cart=1.0, p_sso_login=0.0, failure_injection_rate=0.0)

    respx.get(url__regex=r"^https://shop\.test\.invalid/.*").mock(
        return_value=Response(200, json={"ok": True})
    )
    checkout_route = respx.post("https://shop.test.invalid/api/orders").mock(
        return_value=Response(201, json={"id": 7331, "status": "pending"})
    )

    async with AsyncClient(base_url=cfg.shop_base_url) as client:
        session = Session(cfg, client, tracer)
        outcome = await session.run()

    assert outcome == SessionOutcome.COMPLETED_PURCHASE
    assert checkout_route.called


@respx.mock
async def test_forced_failure_hits_error_path(tracer) -> None:
    dist.set_seed(300)
    cfg = _cfg(
        p_add_to_cart=1.0,
        p_checkout_given_cart=1.0,
        p_sso_login=0.0,
        failure_injection_rate=1.0,  # every session triggers failure
    )

    respx.get(url__regex=r"^https://shop\.test\.invalid/.*").mock(
        return_value=Response(200, json={"ok": True})
    )
    checkout_route = respx.post("https://shop.test.invalid/api/orders").mock(
        return_value=Response(400, json={"error": "invalid payload"})
    )

    async with AsyncClient(base_url=cfg.shop_base_url) as client:
        session = Session(cfg, client, tracer)
        outcome = await session.run()

    assert outcome == SessionOutcome.FAILED_CHECKOUT
    assert checkout_route.called


@respx.mock
async def test_rate_limit_detected(tracer) -> None:
    dist.set_seed(400)
    cfg = _cfg(p_add_to_cart=1.0, p_checkout_given_cart=1.0, p_sso_login=0.0, failure_injection_rate=0.0)

    respx.get(url__regex=r"^https://shop\.test\.invalid/.*").mock(
        return_value=Response(200, json={"ok": True})
    )
    respx.post("https://shop.test.invalid/api/orders").mock(
        return_value=Response(429, json={"error": "slow down"})
    )

    async with AsyncClient(base_url=cfg.shop_base_url) as client:
        session = Session(cfg, client, tracer)
        outcome = await session.run()

    assert outcome == SessionOutcome.RATE_LIMITED
