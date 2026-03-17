"""Session gate — redirects unauthenticated browser requests to /login.

Bypasses:
  - /login, /static/*, /health, /ready, /api/auth/*, favicon.ico
  - API calls (Accept: application/json) — they get 401 instead of redirect
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

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

        # Check session cookie
        from server.modules.auth import get_current_user
        user = get_current_user(request)
        if user:
            return await call_next(request)

        # API calls get a 401 JSON response
        accept = request.headers.get("accept", "")
        if "application/json" in accept or path.startswith("/api/"):
            return JSONResponse({"error": "Authentication required"}, status_code=401)

        # Browser page requests get redirected to login
        return RedirectResponse(url="/login", status_code=302)
