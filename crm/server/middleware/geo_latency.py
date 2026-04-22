"""Geo-latency middleware — simulates region-dependent response times.

Reads the client region from X-Client-Region header, query parameter, or
cookie. Adds artificial latency to simulate real-world geographic distance
from the Frankfurt (eu-central-1) data center.

All delays are logged as span attributes for visibility in OCI APM.
"""

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

# Simulated one-way network latency from eu-central-1 (Frankfurt) datacenter.
# These values represent round-trip-like additional processing delays.
REGION_LATENCY_MS = {
    "eu-central-1": 15,       # local — minimal
    "eu-west-1": 35,          # Ireland
    "eu-north-1": 45,         # Stockholm
    "us-east-1": 90,          # Virginia
    "us-west-2": 160,         # Oregon
    "ca-central-1": 110,      # Montreal
    "ap-southeast-1": 280,    # Singapore
    "ap-northeast-1": 320,    # Tokyo
    "ap-south-1": 250,        # Mumbai
    "sa-east-1": 350,         # São Paulo
    "af-south-1": 400,        # Cape Town
    "me-south-1": 180,        # Bahrain
    "ap-southeast-2": 340,    # Sydney
}

# Friendly names for display
REGION_NAMES = {
    "eu-central-1": "Frankfurt",
    "eu-west-1": "Ireland",
    "eu-north-1": "Stockholm",
    "us-east-1": "N. Virginia",
    "us-west-2": "Oregon",
    "ca-central-1": "Montreal",
    "ap-southeast-1": "Singapore",
    "ap-northeast-1": "Tokyo",
    "ap-south-1": "Mumbai",
    "sa-east-1": "São Paulo",
    "af-south-1": "Cape Town",
    "me-south-1": "Bahrain",
    "ap-southeast-2": "Sydney",
}


def _detect_region(request: Request) -> str:
    """Extract client region from request metadata."""
    # Priority: header > query param > cookie
    region = request.headers.get("x-client-region", "")
    if not region:
        region = request.query_params.get("region", "")
    if not region:
        region = request.cookies.get("client_region", "")
    return region.strip().lower() if region else ""


class GeoLatencyMiddleware(BaseHTTPMiddleware):
    """Add artificial latency based on client geographic region."""

    async def dispatch(self, request: Request, call_next) -> Response:
        region = _detect_region(request)

        if region and region in REGION_LATENCY_MS:
            tracer = get_tracer()
            delay_ms = REGION_LATENCY_MS[region]
            delay_s = delay_ms / 1000.0

            with tracer.start_as_current_span("geo.network_latency") as span:
                span.set_attribute("geo.client_region", region)
                span.set_attribute("geo.region_name", REGION_NAMES.get(region, region))
                span.set_attribute("geo.simulated_latency_ms", delay_ms)
                span.set_attribute("geo.datacenter", "eu-central-1")
                await asyncio.sleep(delay_s)

                if delay_ms > 200:
                    push_log("WARNING", f"High geo-latency for region {region}", **{
                        "geo.client_region": region,
                        "geo.simulated_latency_ms": delay_ms,
                        "http.url.path": request.url.path,
                    })

        response = await call_next(request)

        # Set region header on response for observability
        if region:
            response.headers["X-Served-Region"] = "eu-central-1"
            response.headers["X-Client-Region"] = region
            latency = REGION_LATENCY_MS.get(region, 0)
            response.headers["X-Geo-Latency-Ms"] = str(latency)

        return response
