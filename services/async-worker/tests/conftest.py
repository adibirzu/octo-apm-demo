"""Shared pytest fixtures for the async-worker tests."""

import pytest_asyncio

pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture
async def fake_redis():
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis()
    yield redis
    await redis.aclose()
