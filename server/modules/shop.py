"""Shop module — enhanced marketplace with Juice Shop-inspired vulnerabilities.

Full e-commerce with reviews, coupons, wallet, wishlists.
VULNS: XXE, CSRF, CAPTCHA bypass, coupon manipulation, wallet tampering
"""

import xml.etree.ElementTree as ET
from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api/shop", tags=["shop"])


@router.get("/featured")
async def featured_products():
    """Featured products for storefront landing page."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.featured") as span:
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, name, description, price, image_url, category "
                     "FROM products WHERE is_active = true ORDER BY price DESC LIMIT 8")
            )
            products = [dict(r) for r in result.mappings().all()]
            span.set_attribute("shop.featured_count", len(products))
        return {"products": products}


@router.post("/coupon/apply")
async def apply_coupon(payload: dict, request: Request):
    """Apply coupon — VULN: No rate limit, coupon code brute-forceable."""
    code = payload.get("code", "")
    source_ip = request.client.host if request.client else "unknown"

    tracer = get_tracer()
    with tracer.start_as_current_span("shop.apply_coupon") as span:
        span.set_attribute("shop.coupon_code", code)

        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM coupons WHERE code = :code AND is_active = true"),
                {"code": code},
            )
            coupon = result.mappings().first()

        if not coupon:
            security_span("brute_force", severity="low", payload=code,
                          source_ip=source_ip, endpoint="/api/shop/coupon/apply")
            return {"error": f"Invalid coupon code: {code}", "valid": False}

        return {
            "valid": True,
            "code": code,
            "discount_percent": coupon["discount_percent"],
            "discount_amount": coupon["discount_amount"],
        }


@router.post("/coupon/validate-xml")
async def validate_coupon_xml(request: Request):
    """Validate coupon via XML — VULN: XXE injection."""
    body = await request.body()
    source_ip = request.client.host if request.client else "unknown"

    tracer = get_tracer()
    with tracer.start_as_current_span("shop.validate_coupon_xml") as span:
        try:
            # VULN: XXE — parsing untrusted XML without disabling external entities
            root = ET.fromstring(body)
            code = root.findtext("code", "")
            span.set_attribute("shop.xml_coupon_code", code)

            if "<!ENTITY" in body.decode("utf-8", errors="ignore"):
                security_span("xxe", severity="critical", payload=body.decode()[:200],
                              source_ip=source_ip,
                              endpoint="/api/shop/coupon/validate-xml")

            async with get_db() as db:
                result = await db.execute(
                    text("SELECT * FROM coupons WHERE code = :code"),
                    {"code": code},
                )
                coupon = result.mappings().first()

            if coupon:
                return {"valid": True, "code": code}
            return {"valid": False, "code": code}

        except ET.ParseError as e:
            return {"error": f"Invalid XML: {e}", "valid": False}


@router.post("/checkout")
async def checkout(payload: dict, request: Request):
    """Checkout — VULN: CSRF (no token), client-controlled pricing."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("shop.checkout") as span:
        total = payload.get("total", 0)
        items = payload.get("items", [])

        # VULN: CSRF — no token validation
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not csrf_token:
            security_span("csrf", severity="medium",
                          source_ip=source_ip, endpoint="/api/shop/checkout")

        # VULN: Mass assignment — client sends total
        if "total" in payload:
            security_span("mass_assign", severity="high",
                          payload=f"total={total}",
                          source_ip=source_ip, endpoint="/api/shop/checkout")

        span.set_attribute("shop.item_count", len(items))
        span.set_attribute("shop.total", total)

        return {
            "status": "order_placed",
            "total": total,
            "items": len(items),
            "payment": "processed",
        }


@router.get("/wallet")
async def get_wallet(user_id: int = 0, request: Request = None):
    """Get wallet balance — VULN: IDOR on user_id, no auth."""
    if user_id:
        security_span("idor", severity="medium", payload=f"user_id={user_id}",
                      source_ip=request.client.host if request and request.client else "",
                      endpoint="/api/shop/wallet")

    # Simulated wallet
    return {
        "user_id": user_id or 1,
        "balance": 100.00,
        "currency": "USD",
        "transactions": [
            {"type": "credit", "amount": 100.00, "description": "Welcome bonus"},
        ],
    }


@router.post("/wallet/transfer")
async def wallet_transfer(payload: dict, request: Request):
    """Transfer wallet balance — VULN: Negative amount, no auth."""
    amount = payload.get("amount", 0)
    to_user = payload.get("to_user_id", 0)
    source_ip = request.client.host if request.client else "unknown"

    if amount < 0:
        security_span("mass_assign", severity="critical",
                      payload=f"negative_transfer={amount}",
                      source_ip=source_ip, endpoint="/api/shop/wallet/transfer")

    return {
        "status": "transferred",
        "amount": amount,
        "to_user_id": to_user,
    }


@router.get("/captcha")
async def get_captcha():
    """Get CAPTCHA challenge — VULN: Predictable, solvable client-side."""
    import random
    a, b = random.randint(1, 10), random.randint(1, 10)
    return {
        "challenge": f"What is {a} + {b}?",
        "answer_hash": str(a + b),  # VULN: answer is plaintext, not hashed
        "captcha_id": f"cap-{a}-{b}",
    }


@router.post("/captcha/verify")
async def verify_captcha(payload: dict, request: Request):
    """Verify CAPTCHA — VULN: Answer in response, trivially bypassable."""
    answer = payload.get("answer", "")
    expected = payload.get("expected", "")  # VULN: client sends expected answer

    if str(answer) == str(expected):
        return {"valid": True}

    security_span("captcha_bypass", severity="low",
                  payload=f"answer={answer}",
                  source_ip=request.client.host if request.client else "",
                  endpoint="/api/shop/captcha/verify")
    return {"valid": False}
