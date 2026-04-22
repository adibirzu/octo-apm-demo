"""Geo-latency middleware — simulates network delay by client region."""

import asyncio
import random
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from server.observability.otel_setup import get_tracer

REGION_LATENCY_MS = {
    "eu-central-1": 15,
    "eu-west-1": 30,
    "us-east-1": 90,
    "us-west-2": 120,
    "ca-central-1": 100,
    "ap-southeast-1": 200,
    "ap-northeast-1": 250,
    "ap-southeast-2": 280,
    "sa-east-1": 300,
    "me-south-1": 180,
    "af-south-1": 400,
}


class GeoLatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        region = (
            request.headers.get("x-client-region")
            or request.query_params.get("region", "")
            or request.cookies.get("client_region", "")
        )
        delay_ms = REGION_LATENCY_MS.get(region, 0)

        if delay_ms > 0:
            tracer = get_tracer("geo")
            with tracer.start_as_current_span("geo.network_latency") as span:
                span.set_attribute("geo.client_region", region)
                span.set_attribute("geo.latency_ms", delay_ms)
                actual = int(delay_ms * random.uniform(0.8, 1.2))
                await asyncio.sleep(actual / 1000)

        response = await call_next(request)
        if region:
            response.headers["X-Client-Region"] = region
            response.headers["X-Served-Region"] = "eu-central-1"
            response.headers["X-Geo-Latency-Ms"] = str(delay_ms)
        return response
