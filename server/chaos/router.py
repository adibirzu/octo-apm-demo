"""Shop-side chaos router.

Exposes **read-only** introspection endpoints so that the CRM admin UI and
the Ops portal can confirm what scenario the shop currently observes.
There is deliberately no POST/PUT/DELETE here — writes are CRM-only.
"""

from __future__ import annotations

from fastapi import APIRouter

from server.chaos.registry import PRESETS, get_active_state

router = APIRouter(prefix="/api/chaos", tags=["chaos"])


@router.get("/presets")
def list_presets() -> dict[str, list[dict[str, object]]]:
    return {
        "presets": [
            {
                "id": p.id,
                "description": p.description,
                "targets": list(p.targets),
                "faults": list(p.faults),
                "default_ttl_seconds": p.default_ttl_seconds,
            }
            for p in PRESETS
        ]
    }


@router.get("/state")
def current_state() -> dict[str, object]:
    state = get_active_state()
    if state is None:
        return {"active": False}
    return {"active": True, "state": state.to_json()}
