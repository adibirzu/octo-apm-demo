"""Role-based FastAPI dependencies.

These dependencies wrap the existing session/SSO layer in `auth_security.py`
without modifying it. Import is deferred so test suites can stub the
underlying lookup.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import Depends, HTTPException, Request, status


def _extract_roles(request: Request) -> set[str]:
    """Best-effort role extraction from the current session.

    The shop uses session cookies populated by the SSO flow; we read the
    `roles` claim if present. Falls back to empty set (deny by default).
    """
    session = getattr(request.state, "session", None) or {}
    raw = session.get("roles") or session.get("role") or []
    if isinstance(raw, str):
        raw = [raw]
    return {str(r).strip().lower() for r in raw if r}


def require_role(*required: str) -> "Depends":
    """Return a dependency that enforces membership in any of the roles."""
    expected = {r.strip().lower() for r in required if r.strip()}

    def _dep(request: Request) -> None:
        have = _extract_roles(request)
        if not expected or not have.intersection(expected):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="role_required",
            )

    return Depends(_dep)


def require_any_role(required: Iterable[str]) -> "Depends":
    return require_role(*list(required))
