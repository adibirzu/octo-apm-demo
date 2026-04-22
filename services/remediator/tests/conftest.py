"""Shared fixtures for remediator tests — provides fake_redis."""

import pytest_asyncio

pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture
async def fake_redis():
    import fakeredis.aioredis  # type: ignore

    r = fakeredis.aioredis.FakeRedis()
    yield r
    await r.aclose()
