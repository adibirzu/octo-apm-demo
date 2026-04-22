"""The fuzzer's job is to be **loud** — every request should trip
*something* at the edge (WAF, rate limiter, auth). The point is not
to breach anything; it's to generate visible signal so operators can
verify their alarms + saved searches fire."""

from __future__ import annotations

import asyncio
import logging
import random
import string
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class FuzzStats:
    total: int = 0
    by_status: dict[int, int] = field(default_factory=dict)
    network_errors: int = 0

    def record(self, status: int) -> None:
        self.total += 1
        self.by_status[status] = self.by_status.get(status, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "by_status": dict(self.by_status),
            "network_errors": self.network_errors,
        }


class EdgeFuzzer:
    """Bursts malformed requests at the target endpoint in the pattern
    declared by the load-control profile.

    Categories of malformed requests rotated randomly so the single
    target doesn't memoize one shape:

    1. Missing auth
    2. Wrong API key (random string)
    3. Expired JWT (header-claimed but unsigned)
    4. Oversized body (~10KB)
    5. SQL-injection-shaped path
    6. XSS-shaped query parameter
    """

    def __init__(
        self,
        *,
        target_url: str,
        target_endpoint: str = "/api/admin/chaos/apply",
        requests_count: int = 500,
        concurrency: int = 10,
        run_id: str = "",
        operator: str = "edge-fuzzer",
        logger: logging.Logger | None = None,
    ):
        self._base = target_url.rstrip("/")
        self._endpoint = target_endpoint
        self._count = requests_count
        self._concurrency = concurrency
        self._run_id = run_id
        self._operator = operator
        self.stats = FuzzStats()
        self._logger = logger or logging.getLogger(__name__)

    async def run(self) -> FuzzStats:
        semaphore = asyncio.Semaphore(self._concurrency)

        async with httpx.AsyncClient(timeout=5.0, verify=True) as client:
            tasks = [
                asyncio.create_task(self._one(client, semaphore, i))
                for i in range(self._count)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        self._logger.info("edge_fuzz.summary", extra=self.stats.as_dict())
        return self.stats

    async def _one(self, client: httpx.AsyncClient, sem: asyncio.Semaphore, idx: int) -> None:
        async with sem:
            try:
                resp = await self._request(client, idx)
                self.stats.record(resp.status_code)
            except httpx.HTTPError:
                self.stats.network_errors += 1

    async def _request(self, client: httpx.AsyncClient, idx: int) -> httpx.Response:
        category = idx % 6
        url = f"{self._base}{self._endpoint}"
        headers = self._base_headers()

        if category == 0:
            # Missing auth
            return await client.get(url, headers=headers)
        if category == 1:
            # Wrong API key
            headers["X-API-Key"] = _random(40)
            return await client.get(url, headers=headers)
        if category == 2:
            # Expired/forged JWT
            headers["Authorization"] = "Bearer " + _forged_jwt()
            return await client.get(url, headers=headers)
        if category == 3:
            # Oversized body
            payload = {"note": "a" * 10_000}
            return await client.post(url, headers=headers, json=payload)
        if category == 4:
            # SQLi-shaped path
            return await client.get(
                f"{url}/products?id=1%27%20OR%20%271%27%3D%271",
                headers=headers,
            )
        # category == 5 — XSS query param
        return await client.get(
            f"{url}?search=%3Cscript%3Ealert(1)%3C%2Fscript%3E",
            headers=headers,
        )

    def _base_headers(self) -> dict[str, str]:
        h = {
            "User-Agent": "octo-edge-fuzz/1.0",
            "X-Operator": self._operator,
        }
        if self._run_id:
            h["X-Run-Id"] = self._run_id
        return h


def _random(n: int) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))  # noqa: S311


def _forged_jwt() -> str:
    """Return a syntactically-valid but unsigned JWT. The edge verifier
    should reject it — we don't want to learn otherwise."""
    header = "eyJhbGciOiJub25lIn0"      # base64url({"alg":"none"})
    payload = "eyJzdWIiOiJhdHRhY2tlciJ9"  # base64url({"sub":"attacker"})
    return f"{header}.{payload}."
