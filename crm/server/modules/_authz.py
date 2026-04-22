"""Shared request authorization helpers for protected CRM operations."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

CATALOG_MANAGER_ROLES = {"admin", "manager"}
ADMIN_ROLES = {"admin"}


def get_request_user(request: Request) -> dict | None:
    state_user = getattr(request.state, "current_user", None)
    if state_user:
        return state_user

    from server.modules.auth import get_current_user

    return get_current_user(request)


def require_authenticated_user(request: Request) -> dict:
    user = get_request_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def can_manage_catalog(role: str | None) -> bool:
    return (role or "").strip().lower() in CATALOG_MANAGER_ROLES


def require_admin_user(request: Request) -> dict:
    user = require_authenticated_user(request)
    if (user.get("role") or "").strip().lower() not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return user


def require_management_user(request: Request) -> dict:
    user = require_authenticated_user(request)
    if not can_manage_catalog(user.get("role")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Management role required",
        )
    return user
