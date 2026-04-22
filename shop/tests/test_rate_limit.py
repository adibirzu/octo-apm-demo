"""KG-041 — Redis token bucket tests via fakeredis."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTO_CACHE_URL", raising=False)


async def test_permissive_when_no_redis_configured() -> None:
    from server.modules.rate_limit import check_and_consume

    result = await check_and_consume(key="ip:1.2.3.4", limit=100)
    assert result["allowed"] is True
    assert result["count"] == 0
    assert result["retry_after_seconds"] == 0


async def test_allows_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test")

    import fakeredis.aioredis  # type: ignore

    fake = fakeredis.aioredis.FakeRedis()

    async def _getter():
        return fake

    from server.modules import rate_limit

    monkeypatch.setattr(rate_limit, "_get_redis", _getter)

    for i in range(3):
        result = await rate_limit.check_and_consume(key="ip:x", limit=5)
        assert result["allowed"] is True
    await fake.aclose()


async def test_blocks_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test")

    import fakeredis.aioredis  # type: ignore

    fake = fakeredis.aioredis.FakeRedis()

    async def _getter():
        return fake

    from server.modules import rate_limit

    monkeypatch.setattr(rate_limit, "_get_redis", _getter)

    for _ in range(3):
        result = await rate_limit.check_and_consume(key="ip:y", limit=3)
        assert result["allowed"] is True

    # 4th must be blocked
    result = await rate_limit.check_and_consume(key="ip:y", limit=3)
    assert result["allowed"] is False
    assert result["retry_after_seconds"] > 0
    await fake.aclose()


async def test_redis_error_falls_through_permissive(monkeypatch: pytest.MonkeyPatch) -> None:
    """If Redis itself errors, DO NOT block traffic — the rate limiter
    must never be the cause of an outage."""
    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test")

    class _BrokenRedis:
        def pipeline(self):
            raise RuntimeError("redis offline")

        async def aclose(self):
            return None

    async def _getter():
        return _BrokenRedis()

    from server.modules import rate_limit

    monkeypatch.setattr(rate_limit, "_get_redis", _getter)

    result = await rate_limit.check_and_consume(key="ip:z", limit=1)
    assert result["allowed"] is True  # permissive fallback
