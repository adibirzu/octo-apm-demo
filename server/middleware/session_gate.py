"""Session gate — redirects unauthenticated browser requests to /login.

Bypasses:
  - /login, /static/*, /health, /ready, /api/auth/*, favicon.ico
  - API calls (Accept: application/json) — they get 401 instead of redirect
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

from server.config import cfg

# Dedicated executor for auth lookups. Using `asyncio.to_thread` directly
# would share the default executor with every other blocking call in the
# process, so a burst of unrelated work could queue auth lookups behind it.
# Sizing mirrors the configured auth DB pool (see KB-435).
_auth_executor = ThreadPoolExecutor(
    max_workers=cfg.auth_executor_max_workers,
    thread_name_prefix="auth-lookup",
)

# Admission control: bound the number of auth lookups that can be in-flight
# (running or queued) at once. Without this, a DB stall turns into an
# unbounded queue that grows request memory until the pod OOMs. When the
# semaphore is saturated we immediately return 503 instead of enqueueing,
# letting clients retry with the Retry-After header rather than piling on.
# Capacity = executor workers * 2 so brief bursts can queue up to one extra
# batch, but sustained pressure sheds load fast.
_auth_inflight = asyncio.Semaphore(cfg.auth_executor_max_workers * 2)

# Hard per-lookup wall-clock cap. Even once a worker picks up the task, we
# must not let a hung Oracle connection keep an executor slot forever; the
# DB pool_timeout (5s) is the happy-path cap, and this is the circuit-break.
_AUTH_LOOKUP_TIMEOUT_S = 8.0

# Paths that never require auth
_PUBLIC_PREFIXES = (
    "/login", "/static/", "/health", "/ready", "/metrics", "/api/auth/", "/favicon",
    # Cross-service endpoints used by octo-drone-shop and internal integrations
    "/api/customers", "/api/invoices", "/api/tickets", "/api/orders",
    "/api/integrations", "/api/observability/", "/api/analytics/track",
)


class SessionGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow public paths
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # Check session cookie. `get_current_user` raises
        # `SessionLookupUnavailable` when the session store itself is
        # unreachable — we MUST NOT treat that as "no session", because doing
        # so turns any DB outage (e.g. ATP credential rotation, see KB-435)
        # into a fleet-wide forced logout. Return 503 instead so users remain
        # signed in once the backend recovers.
        from server.modules.auth import get_current_user, SessionLookupUnavailable
        accept = request.headers.get("accept", "")
        wants_json = "application/json" in accept or path.startswith("/api/")

        def _unavailable(reason: str):
            return JSONResponse(
                {"error": "Authentication service temporarily unavailable", "reason": reason},
                status_code=503,
                headers={"Retry-After": "5"},
            )

        # Admission control: if we can't acquire a slot within 500ms, the
        # auth path is saturated — return 503 now rather than let the queue
        # grow unbounded during a DB incident.
        try:
            await asyncio.wait_for(_auth_inflight.acquire(), timeout=0.5)
        except asyncio.TimeoutError:
            return _unavailable("auth_saturated")

        try:
            # `get_current_user` does a blocking sync DB lookup (pool_pre_ping
            # + SELECT). Offload to our dedicated bounded executor so:
            #   - the event loop never blocks on Oracle latency
            #   - auth lookups are isolated from unrelated blocking work
            #   - `wait_for` enforces a hard upper bound even if the worker
            #     gets stuck on a hung connection.
            loop = asyncio.get_running_loop()
            try:
                user = await asyncio.wait_for(
                    loop.run_in_executor(_auth_executor, get_current_user, request),
                    timeout=_AUTH_LOOKUP_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                return _unavailable("auth_timeout")
            except SessionLookupUnavailable:
                return _unavailable("auth_backend_error")
        finally:
            _auth_inflight.release()

        if user:
            request.state.current_user = user
            return await call_next(request)

        # API calls get a 401 JSON response
        if wants_json:
            return JSONResponse({"error": "Authentication required"}, status_code=401)

        # Browser page requests get redirected to login
        return RedirectResponse(url="/login", status_code=302)
