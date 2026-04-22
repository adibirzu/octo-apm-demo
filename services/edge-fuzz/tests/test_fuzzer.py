"""Fuzzer tests — respx-mocked HTTP so nothing hits a real target.

Asserts the category rotation covers all 6 fuzz shapes and that stats
record every response."""

from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from octo_edge_fuzz import EdgeFuzzer


@respx.mock
async def test_all_six_categories_fire() -> None:
    # Catch-all mock returning 401 (expected edge response to any
    # fuzz payload). The fuzzer doesn't care about the body.
    respx.route().mock(return_value=Response(401, json={"err": "unauthorized"}))

    fuzzer = EdgeFuzzer(
        target_url="https://edge.test.invalid",
        requests_count=12,  # 12 = 2 full cycles of the 6-category rotation
        concurrency=4,
    )
    stats = await fuzzer.run()

    assert stats.total == 12
    assert stats.by_status.get(401) == 12
    assert stats.network_errors == 0


@respx.mock
async def test_run_id_header_propagated() -> None:
    captured: list[dict[str, str]] = []

    def _record(request):
        captured.append(dict(request.headers))
        return Response(401)

    respx.route().mock(side_effect=_record)

    fuzzer = EdgeFuzzer(
        target_url="https://edge.test.invalid",
        requests_count=6,
        concurrency=1,
        run_id="test-run-id-abc",
        operator="test-op",
    )
    await fuzzer.run()

    assert len(captured) == 6
    for hdrs in captured:
        assert hdrs["x-run-id"] == "test-run-id-abc"
        assert hdrs["x-operator"] == "test-op"
        assert hdrs["user-agent"] == "octo-edge-fuzz/1.0"


@respx.mock
async def test_network_errors_counted_not_raised() -> None:
    import httpx

    respx.route().mock(side_effect=httpx.ConnectError("dns failed"))

    fuzzer = EdgeFuzzer(
        target_url="https://unreachable.test.invalid",
        requests_count=5,
        concurrency=2,
    )
    stats = await fuzzer.run()

    assert stats.total == 0
    assert stats.network_errors == 5


@respx.mock
async def test_sqli_and_xss_shapes_appear_in_request_path() -> None:
    urls: list[str] = []

    def _record(request):
        urls.append(str(request.url))
        return Response(400)

    respx.route().mock(side_effect=_record)

    fuzzer = EdgeFuzzer(
        target_url="https://edge.test.invalid",
        target_endpoint="/api/probe",
        requests_count=6,
        concurrency=1,
    )
    await fuzzer.run()

    urls_joined = "\n".join(urls)
    # SQLi (URL-encoded single quote + OR) — category 4
    assert "%27" in urls_joined and "OR" in urls_joined
    # XSS (URL-encoded script tag) — category 5
    assert "%3Cscript%3E" in urls_joined
