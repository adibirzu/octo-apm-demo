"""Chaos engineering middleware — inject failures on demand."""

import asyncio
import random
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class ChaosState:
    db_latency_ms: int = 0
    db_disconnect: bool = False
    error_rate: float = 0.0
    slow_responses: bool = False


chaos = ChaosState()


class ChaosMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/simulate"):
            return await call_next(request)

        if chaos.error_rate > 0 and random.random() < chaos.error_rate:
            return JSONResponse(
                {"error": "Chaos: simulated error burst", "chaos": True},
                status_code=500,
            )

        if chaos.slow_responses:
            await asyncio.sleep(random.uniform(2, 5))

        return await call_next(request)
