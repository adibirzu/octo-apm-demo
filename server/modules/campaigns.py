"""Campaigns module — marketing campaigns and lead management."""

import html
import re

from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api", tags=["campaigns"])


def _sanitize(value: str, max_len: int = 500) -> str:
    """Strip HTML tags and escape content."""
    stripped = re.sub(r"<[^>]+>", "", str(value))
    return html.escape(stripped, quote=True)[:max_len]


@router.get("/campaigns")
async def list_campaigns():
    """List campaigns with lead counts in a single query (no N+1)."""
    tracer = get_tracer()
    with tracer.start_as_current_span("campaigns.list") as span:
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT c.*, COALESCE(lc.cnt, 0) AS lead_count "
                    "FROM campaigns c "
                    "LEFT JOIN (SELECT campaign_id, COUNT(*) AS cnt FROM leads GROUP BY campaign_id) lc "
                    "ON lc.campaign_id = c.id "
                    "ORDER BY c.created_at DESC"
                )
            )
            campaigns = [dict(r) for r in result.mappings().all()]
            span.set_attribute("db.row_count", len(campaigns))
        return {"campaigns": campaigns}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int):
    """Get campaign details with leads."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT * FROM campaigns WHERE id = :id"), {"id": campaign_id}
        )
        campaign = result.mappings().first()

    if not campaign:
        return {"error": "Campaign not found"}

    # Also fetch leads for this campaign
    async with get_db() as db:
        leads_result = await db.execute(
            text("SELECT * FROM leads WHERE campaign_id = :cid ORDER BY score DESC"),
            {"cid": campaign_id},
        )
        leads = [dict(r) for r in leads_result.mappings().all()]

    return {**dict(campaign), "leads": leads}


@router.post("/campaigns")
async def create_campaign(payload: dict):
    """Create campaign with validated fields (spent is server-controlled)."""
    name = _sanitize(payload.get("name", "Untitled"), 200)
    campaign_type = _sanitize(payload.get("campaign_type", "email"), 50)
    status = payload.get("status", "draft")
    if status not in ("draft", "active", "paused", "completed"):
        status = "draft"

    budget = max(0, float(payload.get("budget", 0) or 0))
    audience = _sanitize(payload.get("target_audience", ""), 500)

    async with get_db() as db:
        await db.execute(
            text("INSERT INTO campaigns (name, campaign_type, status, budget, spent, target_audience) "
                 "VALUES (:name, :campaign_type, :status, :budget, 0, :audience)"),
            {
                "name": name,
                "campaign_type": campaign_type,
                "status": status,
                "budget": budget,
                "audience": audience,
            },
        )
    return {"status": "created"}


@router.get("/campaigns/{campaign_id}/leads")
async def list_leads(campaign_id: int):
    """List leads for a campaign."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT * FROM leads WHERE campaign_id = :cid ORDER BY score DESC"),
            {"cid": campaign_id},
        )
        return {"leads": [dict(r) for r in result.mappings().all()]}


@router.post("/campaigns/{campaign_id}/leads")
async def create_lead(campaign_id: int, payload: dict):
    """Create lead with sanitized input."""
    email = _sanitize(payload.get("email", ""), 200)
    name = _sanitize(payload.get("name", ""), 100)
    source = _sanitize(payload.get("source", "web"), 50)
    notes = _sanitize(payload.get("notes", ""), 1000)

    if not email:
        return {"error": "Email is required"}

    async with get_db() as db:
        # Verify campaign exists
        exists = await db.execute(
            text("SELECT id FROM campaigns WHERE id = :cid"), {"cid": campaign_id}
        )
        if not exists.first():
            return {"error": "Campaign not found"}

        await db.execute(
            text("INSERT INTO leads (campaign_id, email, name, source, notes) "
                 "VALUES (:cid, :email, :name, :source, :notes)"),
            {"cid": campaign_id, "email": email, "name": name, "source": source, "notes": notes},
        )
    return {"status": "created"}
