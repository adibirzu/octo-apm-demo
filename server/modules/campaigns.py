"""Campaigns module — marketing campaigns and lead management.

VULNS: N+1 queries, stored XSS in lead notes, mass assignment on spent
"""

from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api", tags=["campaigns"])


@router.get("/campaigns")
async def list_campaigns():
    """List campaigns — VULN: N+1 query pattern for lead counts."""
    tracer = get_tracer()
    with tracer.start_as_current_span("campaigns.list") as span:
        async with get_db() as db:
            result = await db.execute(text("SELECT * FROM campaigns ORDER BY created_at DESC"))
            campaigns = [dict(r) for r in result.mappings().all()]

            # VULN: N+1 — one query per campaign for lead count
            for camp in campaigns:
                with tracer.start_as_current_span("db.query.lead_count") as q_span:
                    lr = await db.execute(
                        text("SELECT COUNT(*) FROM leads WHERE campaign_id = :cid"),
                        {"cid": camp["id"]},
                    )
                    camp["lead_count"] = lr.scalar()
                    q_span.set_attribute("campaign.id", camp["id"])

            span.set_attribute("db.row_count", len(campaigns))
        return {"campaigns": campaigns}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, request: Request):
    """Get campaign — VULN: IDOR."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT * FROM campaigns WHERE id = :id"), {"id": campaign_id}
        )
        campaign = result.mappings().first()

    if not campaign:
        security_span("idor", severity="low", payload=str(campaign_id),
                      source_ip=request.client.host if request.client else "",
                      endpoint=f"/api/campaigns/{campaign_id}")
        return {"error": "Campaign not found"}
    return dict(campaign)


@router.post("/campaigns")
async def create_campaign(payload: dict, request: Request):
    """Create campaign — VULN: Mass assignment allows setting 'spent'."""
    source_ip = request.client.host if request.client else "unknown"

    if "spent" in payload:
        security_span("mass_assign", severity="high",
                      payload=f"spent={payload['spent']}",
                      source_ip=source_ip, endpoint="/api/campaigns")

    async with get_db() as db:
        await db.execute(
            text("INSERT INTO campaigns (name, campaign_type, status, budget, spent, target_audience) "
                 "VALUES (:name, :type, :status, :budget, :spent, :audience)"),
            {
                "name": payload.get("name", "Untitled"),
                "type": payload.get("campaign_type", "email"),
                "status": payload.get("status", "draft"),
                "budget": payload.get("budget", 0),
                "spent": payload.get("spent", 0),  # VULN: client-controlled
                "audience": payload.get("target_audience", ""),
            },
        )
    return {"status": "created"}


@router.get("/campaigns/{campaign_id}/leads")
async def list_leads(campaign_id: int):
    """List leads for campaign — VULN: No auth."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT * FROM leads WHERE campaign_id = :cid ORDER BY score DESC"),
            {"cid": campaign_id},
        )
        return {"leads": [dict(r) for r in result.mappings().all()]}


@router.post("/campaigns/{campaign_id}/leads")
async def create_lead(campaign_id: int, payload: dict, request: Request):
    """Create lead — VULN: Stored XSS in notes field."""
    source_ip = request.client.host if request.client else "unknown"
    notes = payload.get("notes", "")

    if "<script" in notes.lower() or "onerror" in notes.lower():
        security_span("xss", severity="high", payload=notes,
                      source_ip=source_ip,
                      endpoint=f"/api/campaigns/{campaign_id}/leads")

    async with get_db() as db:
        await db.execute(
            text("INSERT INTO leads (campaign_id, email, name, source, notes) "
                 "VALUES (:cid, :email, :name, :source, :notes)"),
            {
                "cid": campaign_id,
                "email": payload.get("email", ""),
                "name": payload.get("name", ""),
                "source": payload.get("source", "web"),
                "notes": notes,
            },
        )
    return {"status": "created"}
