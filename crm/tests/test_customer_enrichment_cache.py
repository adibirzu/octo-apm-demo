"""KG-026 — CRM customer-enrichment cache tests."""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTO_CACHE_URL", raising=False)


async def test_empty_email_returns_none() -> None:
    from server.modules import customer_enrichment as ce

    assert await ce.find_customer_by_email("") is None


async def test_no_cache_falls_through_to_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.modules import customer_enrichment as ce

    async def _fake_db(email: str):
        return {"id": 1, "email": email, "name": "A"}

    monkeypatch.setattr(ce, "_find_by_email_in_db", _fake_db)

    result = await ce.find_customer_by_email("a@example.invalid")
    assert result["id"] == 1


async def test_cache_hit_skips_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.modules import customer_enrichment as ce

    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test")

    class _FakeCache:
        async def get(self, ns, key):
            return json.dumps({"id": 42, "email": "cached@x", "name": "Cached"}).encode()

        async def set(self, *a, **kw):
            pass

        async def aclose(self):
            pass

    async def _cache_getter():
        return _FakeCache()

    db_hits = 0

    async def _fake_db(email: str):
        nonlocal db_hits
        db_hits += 1
        return None

    monkeypatch.setattr(ce, "_get_cache", _cache_getter)
    monkeypatch.setattr(ce, "_find_by_email_in_db", _fake_db)

    result = await ce.find_customer_by_email("cached@x")
    assert result["id"] == 42
    assert db_hits == 0


async def test_cache_miss_populates_with_correct_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    from server.modules import customer_enrichment as ce

    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test")
    set_calls = []

    class _FakeCache:
        async def get(self, ns, key):
            return None

        async def set(self, ns, key, value, *, ttl_seconds):
            set_calls.append((ns, key, ttl_seconds))

        async def aclose(self):
            pass

    async def _cache_getter():
        return _FakeCache()

    async def _fake_db(email: str):
        return {"id": 5, "email": email, "name": "B"}

    monkeypatch.setattr(ce, "_get_cache", _cache_getter)
    monkeypatch.setattr(ce, "_find_by_email_in_db", _fake_db)

    result = await ce.find_customer_by_email("b@example.invalid")
    assert result["id"] == 5
    assert len(set_calls) == 1
    assert set_calls[0][0] == "crm:customer"
    assert "by-email" in set_calls[0][1]
    assert set_calls[0][2] == 300


async def test_nonexistent_email_cached_as_empty_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caching misses too — otherwise repeated lookups for a bad email
    hammer the DB for the whole TTL window."""
    from server.modules import customer_enrichment as ce

    monkeypatch.setenv("OCTO_CACHE_URL", "redis://test")
    set_calls = []

    class _FakeCache:
        async def get(self, ns, key):
            return None

        async def set(self, ns, key, value, *, ttl_seconds):
            set_calls.append(value)

        async def aclose(self):
            pass

    async def _cache_getter():
        return _FakeCache()

    async def _fake_db(email: str):
        return None

    monkeypatch.setattr(ce, "_get_cache", _cache_getter)
    monkeypatch.setattr(ce, "_find_by_email_in_db", _fake_db)

    result = await ce.find_customer_by_email("ghost@x")
    assert result is None
    # Miss cached as empty dict
    assert set_calls[0] == "{}"
