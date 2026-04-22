"""Campaign & lead management module — OWASP A01: Broken Access Control + A03: Injection.

Vulnerabilities:
- IDOR in campaign detail (no ownership check)
- Mass assignment (client can set 'spent' field)
- Stored XSS in lead notes
- No auth check on lead listing
- No ownership validation on lead status update
- N+1 query pattern in campaign listing (APM demo)
"""

import asyncio

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics
from server.database import Campaign, Lead, get_db

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])
tracer_fn = get_tracer


@router.get("")
async def list_campaigns(
    request: Request,
    status: str = Query(default="", description="Filter by status"),
    campaign_type: str = Query(default="", description="Filter by type"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List campaigns with N+1 pattern — loads leads per campaign individually for APM demo."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("campaigns.list") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.campaigns_list"):
                query = "SELECT * FROM campaigns WHERE 1=1"
                params = {}
                if status:
                    query += " AND status = :status"
                    params["status"] = status
                if campaign_type:
                    query += " AND campaign_type = :ctype"
                    params["ctype"] = campaign_type
                query += " ORDER BY created_at DESC"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

            campaigns = []
            # N+1 pattern: load leads for each campaign individually
            for row in rows:
                campaign = dict(row._mapping)
                with tracer.start_as_current_span("db.query.campaign_leads_count") as lead_span:
                    lead_span.set_attribute("campaign.id", campaign["id"])
                    lead_result = await db.execute(
                        text("SELECT COUNT(*) as cnt FROM leads WHERE campaign_id = :cid"),
                        {"cid": campaign["id"]}
                    )
                    lead_count = lead_result.fetchone()
                    campaign["lead_count"] = lead_count[0] if lead_count else 0
                campaigns.append(campaign)

        span.set_attribute("campaigns.count", len(campaigns))
        return {"campaigns": campaigns, "total": len(campaigns), "limit": limit, "offset": offset}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, request: Request):
    """Get campaign detail with lead stats — VULN: IDOR (no ownership check)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("campaigns.get") as span:
        span.set_attribute("campaign.id", campaign_id)

        # VULN: IDOR — no check that requesting user owns this campaign
        with security_span("idor", severity="medium",
                         payload=f"campaign_id={campaign_id}",
                         source_ip=client_ip):
            log_security_event("idor", "medium",
                f"Campaign accessed without ownership check: {campaign_id}",
                source_ip=client_ip)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.campaign_detail"):
                result = await db.execute(
                    text("SELECT * FROM campaigns WHERE id = :id"), {"id": campaign_id}
                )
                campaign = result.fetchone()

            if not campaign:
                return {"error": "Campaign not found"}

            with tracer.start_as_current_span("db.query.campaign_lead_stats"):
                stats_result = await db.execute(
                    text("SELECT status, COUNT(*) as cnt FROM leads "
                         "WHERE campaign_id = :cid GROUP BY status"),
                    {"cid": campaign_id}
                )
                lead_stats = {r[0]: r[1] for r in stats_result.fetchall()}

            with tracer.start_as_current_span("db.query.campaign_total_leads"):
                total_result = await db.execute(
                    text("SELECT COUNT(*) FROM leads WHERE campaign_id = :cid"),
                    {"cid": campaign_id}
                )
                total_leads = total_result.fetchone()[0]

        return {
            "campaign": dict(campaign._mapping),
            "lead_stats": lead_stats,
            "total_leads": total_leads,
        }


@router.post("")
async def create_campaign(request: Request):
    """Create campaign — VULN: mass assignment (accepts 'spent' from client)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("campaigns.create") as span:
        # VULN: mass assignment — client can set 'spent' field directly
        if "spent" in body:
            with security_span("mass_assignment", severity="high",
                             payload=f"spent={body['spent']}",
                             source_ip=client_ip):
                log_security_event("mass_assignment", "high",
                    f"Client set 'spent' field directly: {body['spent']}",
                    source_ip=client_ip, payload=str(body))

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.campaign_insert"):
                campaign = Campaign(
                    name=body.get("name", "Untitled Campaign"),
                    campaign_type=body.get("campaign_type", "email"),
                    status=body.get("status", "draft"),
                    budget=body.get("budget", 0.0),
                    spent=body.get("spent", 0.0),  # VULN: mass assignment
                    target_audience=body.get("target_audience", ""),
                    start_date=body.get("start_date"),
                    end_date=body.get("end_date"),
                    created_by=body.get("created_by"),
                )
                db.add(campaign)
                await db.flush()
                campaign_id = campaign.id

        business_metrics.record_campaign_created(campaign_type=body.get("campaign_type", "email"))
        push_log("INFO", f"Campaign #{campaign_id} created", **{
            "campaign.id": campaign_id,
            "campaign.name": body.get("name", ""),
            "campaign.type": body.get("campaign_type", "email"),
        })
        return {"status": "created", "campaign_id": campaign_id}


@router.get("/{campaign_id}/leads")
async def list_campaign_leads(
    campaign_id: int,
    request: Request,
    status: str = Query(default="", description="Filter by lead status"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List leads for campaign — VULN: no auth check."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("campaigns.leads.list") as span:
        span.set_attribute("campaign.id", campaign_id)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.campaign_leads"):
                query = ("SELECT l.*, c.name as customer_name FROM leads l "
                         "LEFT JOIN customers c ON l.customer_id = c.id "
                         "WHERE l.campaign_id = :cid")
                params = {"cid": campaign_id}
                if status:
                    query += " AND l.status = :status"
                    params["status"] = status
                query += " ORDER BY l.created_at DESC"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        leads = [dict(r._mapping) for r in rows]
        return {"leads": leads, "total": len(leads), "limit": limit, "offset": offset}


@router.post("/{campaign_id}/leads")
async def create_lead(campaign_id: int, request: Request):
    """Create lead — VULN: stored XSS in notes field."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("campaigns.leads.create") as span:
        notes = body.get("notes", "")

        # Detect XSS in notes
        if notes and ("<script" in notes.lower() or "onerror" in notes.lower()
                      or "javascript:" in notes.lower()):
            with security_span("xss", severity="high",
                             payload=notes[:200],
                             source_ip=client_ip):
                log_security_event("xss", "high",
                    "Stored XSS detected in lead notes",
                    source_ip=client_ip, payload=notes[:200])

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.lead_insert"):
                lead = Lead(
                    campaign_id=campaign_id,
                    customer_id=body.get("customer_id"),
                    email=body.get("email", ""),
                    name=body.get("name", ""),
                    source=body.get("source", "web"),
                    status="new",
                    score=body.get("score", 0),
                    notes=notes,  # VULN: stored XSS — no sanitization
                )
                db.add(lead)
                await db.flush()
                lead_id = lead.id

        business_metrics.record_lead_captured(source=body.get("source", "web"))
        push_log("INFO", f"Lead #{lead_id} created for campaign #{campaign_id}", **{
            "lead.id": lead_id,
            "campaign.id": campaign_id,
            "lead.email": body.get("email", ""),
            "lead.source": body.get("source", "web"),
        })
        return {"status": "created", "lead_id": lead_id, "campaign_id": campaign_id}


@router.patch("/{campaign_id}/leads/{lead_id}")
async def update_lead_status(campaign_id: int, lead_id: int, request: Request):
    """Update lead status — VULN: no ownership validation."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()
    new_status = body.get("status", "")

    with tracer.start_as_current_span("campaigns.leads.update") as span:
        span.set_attribute("campaign.id", campaign_id)
        span.set_attribute("lead.id", lead_id)
        span.set_attribute("lead.new_status", new_status)

        # VULN: no ownership validation — any user can update any lead
        with security_span("broken_access_control", severity="medium",
                         payload=f"lead_id={lead_id} status={new_status}",
                         source_ip=client_ip):
            log_security_event("broken_access_control", "medium",
                f"Lead status updated without ownership check: lead={lead_id}",
                source_ip=client_ip)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.lead_status_update"):
                # VULN: doesn't verify campaign_id matches lead's actual campaign
                update_fields = "status = :status"
                params = {"status": new_status, "lid": lead_id}

                if new_status == "converted":
                    update_fields += ", converted_at = CURRENT_TIMESTAMP"

                if "score" in body:
                    update_fields += ", score = :score"
                    params["score"] = body["score"]

                if "notes" in body:
                    update_fields += ", notes = :notes"
                    params["notes"] = body["notes"]

                await db.execute(
                    text(f"UPDATE leads SET {update_fields} WHERE id = :lid"),
                    params
                )

        if new_status in ("qualified", "converted"):
            business_metrics.record_lead_converted(new_status=new_status)
        push_log("INFO", f"Lead #{lead_id} status updated to '{new_status}'", **{
            "lead.id": lead_id,
            "campaign.id": campaign_id,
            "lead.new_status": new_status,
        })
        return {"status": "updated", "lead_id": lead_id, "new_status": new_status}
