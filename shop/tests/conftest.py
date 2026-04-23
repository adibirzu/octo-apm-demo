"""Shop test bootstrap.

Puts the shop root on sys.path so `from server.xxx import ...` resolves,
and exposes shared fixtures (fakeredis, module-stub helper, test env
cleaners) that individual tests would otherwise re-define inline.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any, Callable

import pytest

SHOP_ROOT = Path(__file__).resolve().parent.parent
if str(SHOP_ROOT) not in sys.path:
    sys.path.insert(0, str(SHOP_ROOT))


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip host-level env that would bias tests.

    Each test opts into the env it needs via monkeypatch.setenv.
    """
    for var in (
        "OCTO_CACHE_URL",
        "OCTO_ORDER_STREAM_REDIS_URL",
        "OCTO_ASYNC_ORDER_SYNC_ENABLED",
        "OCTO_RATE_LIMIT_REDIS_URL",
        "OCTO_PLATFORM_STATUS_TARGETS",
        "OCI_LOG_OCID",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENV", "test")


@pytest.fixture
def fake_redis():
    """Async FakeRedis instance; closed after test."""
    import fakeredis.aioredis  # type: ignore

    fake = fakeredis.aioredis.FakeRedis()
    try:
        yield fake
    finally:
        # aclose is async — sync tests simply drop the ref
        pass


@pytest.fixture
def stub_module(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, dict[str, Any]], types.ModuleType]:
    """Inject a fake module into sys.modules for the duration of the test.

    Usage:
        stub_module("server.modules.orders", {"_get_order_for_partner_api": fn})

    Returns the inserted ModuleType so the caller can attach extra attrs.
    """

    def _install(dotted: str, attrs: dict[str, Any]) -> types.ModuleType:
        mod = types.ModuleType(dotted)
        for key, val in attrs.items():
            setattr(mod, key, val)
        monkeypatch.setitem(sys.modules, dotted, mod)
        return mod

    return _install


@pytest.fixture
def app_factory():
    """Build a FastAPI app wrapping a single router.

    Keeps individual tests from needing to import FastAPI + TestClient
    boilerplate; returns a callable so tests can customize.
    """
    from fastapi import FastAPI

    def _make(*routers) -> FastAPI:
        app = FastAPI()
        for r in routers:
            app.include_router(r)
        return app

    return _make
