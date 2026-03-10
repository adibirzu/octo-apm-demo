"""Storefront presentation helpers for the OCTO drone catalog."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote


ADDITIONAL_PRODUCTS = [
    {
        "name": "Teledyne FLIR SIRAS",
        "sku": "DRN-009",
        "description": "Industrial inspection drone with visible + thermal payload, secure U.S. data handling, and 31min flight time.",
        "price": 9695.00,
        "stock": 14,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_009.jpg",
    },
    {
        "name": "Inspired Flight IF800 TOMCAT",
        "sku": "DRN-010",
        "description": "Heavy-lift enterprise quad with U.S.-built airframe, 54min endurance, and interchangeable payload rails.",
        "price": 18450.00,
        "stock": 9,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_010.jpg",
    },
    {
        "name": "Gremsy T7 Gimbal",
        "sku": "GMB-002",
        "description": "3-axis mapping and inspection gimbal supporting Sony Alpha payloads with quick-release integration.",
        "price": 3150.00,
        "stock": 18,
        "category": "Cameras & Gimbals",
        "image_url": "/static/img/products/gmb_002.jpg",
    },
    {
        "name": "Hitec X2 AC Plus Black Edition",
        "sku": "BAT-003",
        "description": "Dual-channel intelligent charger for LiPo field operations with storage and balance modes.",
        "price": 189.00,
        "stock": 70,
        "category": "Batteries",
        "image_url": "/static/img/products/bat_003.jpg",
    },
    {
        "name": "CubePilot Here4 GNSS",
        "sku": "FLC-003",
        "description": "High-precision multi-band GNSS + RTK heading module for Pixhawk and ArduPilot stacks.",
        "price": 329.00,
        "stock": 55,
        "category": "Flight Controllers",
        "image_url": "/static/img/products/flc_003.jpg",
    },
    {
        "name": "Doodle Labs Smart Radio",
        "sku": "FPV-003",
        "description": "Industrial mesh radio for BVLOS data links with AES encryption and multi-kilometer reach.",
        "price": 1899.00,
        "stock": 22,
        "category": "FPV Gear",
        "image_url": "/static/img/products/fpv_003.jpg",
    },
    {
        "name": "Foxtech Nimbus VTOL Airframe",
        "sku": "FRM-003",
        "description": "Composite VTOL frame for mapping missions with 120min cruise capability and modular payload bay.",
        "price": 1499.00,
        "stock": 16,
        "category": "Frames",
        "image_url": "/static/img/products/frm_003.jpg",
    },
    {
        "name": "Tronair Payload Transit Case",
        "sku": "ACC-003",
        "description": "Hard transport case with laser-cut foam for enterprise drone fleets and payload kits.",
        "price": 459.00,
        "stock": 44,
        "category": "Accessories",
        "image_url": "/static/img/products/acc_003.jpg",
    },
    {
        "name": "Phantom Racer X1",
        "sku": "OCTO-001",
        "description": "Engineered for blistering speed and unmatched agility.",
        "price": 499.99,
        "stock": 150,
        "category": "Racing Drones",
        "image_url": "/static/img/products/octo_001.jpg",
    },
    {
        "name": "Vortex Pro FPV",
        "sku": "OCTO-002",
        "description": "Immersive first-person view racing with exceptional control.",
        "price": 629.50,
        "stock": 120,
        "category": "Racing Drones",
        "image_url": "/static/img/products/octo_002.jpg",
    },
    {
        "name": "Ignite Micro Racer",
        "sku": "OCTO-003",
        "description": "Designed for indoor racing fun and tight obstacle courses.",
        "price": 179.00,
        "stock": 250,
        "category": "Racing Drones",
        "image_url": "/static/img/products/octo_003.jpg",
    },
    {
        "name": "SkyLens 4K Pro",
        "sku": "OCTO-004",
        "description": "Capture breathtaking aerial footage with a 3-axis gimbal.",
        "price": 1299.99,
        "stock": 80,
        "category": "Camera Drones",
        "image_url": "/static/img/products/octo_004.jpg",
    },
    {
        "name": "AeroFold Mini",
        "sku": "OCTO-005",
        "description": "Your perfect travel companion, easily folding down to fit in any bag.",
        "price": 349.95,
        "stock": 180,
        "category": "Camera Drones",
        "image_url": "/static/img/products/octo_005.jpg",
    },
    {
        "name": "CinemaFly Xtreme",
        "sku": "OCTO-006",
        "description": "Designed for professional filmmakers with interchangeable lenses.",
        "price": 3500.00,
        "stock": 60,
        "category": "Camera Drones",
        "image_url": "/static/img/products/octo_006.jpg",
    },
    {
        "name": "TerraSurvey RTK",
        "sku": "OCTO-007",
        "description": "Precision mapping and surveying with RTK GPS.",
        "price": 9500.00,
        "stock": 50,
        "category": "Industrial Drones",
        "image_url": "/static/img/products/octo_007.jpg",
    },
    {
        "name": "InspectMaster Thermal",
        "sku": "OCTO-008",
        "description": "Detailed inspections with high-resolution thermal camera.",
        "price": 7200.00,
        "stock": 70,
        "category": "Industrial Drones",
        "image_url": "/static/img/products/octo_008.jpg",
    },
    {
        "name": "AgriSprayer Pro",
        "sku": "OCTO-009",
        "description": "Optimize crop health with efficient and precise payload application.",
        "price": 11000.00,
        "stock": 55,
        "category": "Industrial Drones",
        "image_url": "/static/img/products/octo_009.jpg",
    },
    {
        "name": "Extra Flight Battery Pack",
        "sku": "OCTO-010",
        "description": "Extend your flight time with an additional high-capacity LiPo battery.",
        "price": 49.99,
        "stock": 400,
        "category": "Accessories",
        "image_url": "/static/img/products/octo_010.jpg",
    },
    {
        "name": "Propeller Guard Set",
        "sku": "OCTO-011",
        "description": "Protect your drone and surroundings with this durable guard set.",
        "price": 19.95,
        "stock": 500,
        "category": "Accessories",
        "image_url": "/static/img/products/octo_011.jpg",
    },
    {
        "name": "Rugged Carrying Case",
        "sku": "OCTO-012",
        "description": "Safely transport your drone with this custom-fitted rugged case.",
        "price": 120.00,
        "stock": 200,
        "category": "Accessories",
        "image_url": "/static/img/products/octo_012.jpg",
    },
    {
        "name": "Aeronavics SkyJib-8",
        "sku": "DRN-011",
        "description": "Heavy-lift octocopter for cinema and industrial payloads with 12kg capacity and 25min flight.",
        "price": 32500.00,
        "stock": 5,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_011.jpg",
    },
    {
        "name": "T-Motor U8 II KV100",
        "sku": "MOT-002",
        "description": "High-torque brushless motor for heavy-lift multi-rotors, 100KV, IP56 rated.",
        "price": 279.00,
        "stock": 90,
        "category": "Motors & ESCs",
        "image_url": "/static/img/products/mot_002.jpg",
    },
    {
        "name": "Sony ILX-LR1 Aerial Camera",
        "sku": "CAM-002",
        "description": "Compact full-frame 61MP camera for drone mapping with GPS tagging and remote trigger.",
        "price": 3499.00,
        "stock": 20,
        "category": "Cameras & Gimbals",
        "image_url": "/static/img/products/cam_002.jpg",
    },
    {
        "name": "T-Motor G40x13 Folding Props (pair)",
        "sku": "PRP-003",
        "description": "Large folding carbon fiber props for heavy-lift drones with quick-release mounting.",
        "price": 159.00,
        "stock": 120,
        "category": "Propellers",
        "image_url": "/static/img/products/prp_003.jpg",
    },
    {
        "name": "FLIR Vue TZ20-R Thermal Module",
        "sku": "ACC-004",
        "description": "Dual thermal + visible camera module with radiometric temperature measurement for drone inspections.",
        "price": 4995.00,
        "stock": 15,
        "category": "Accessories",
        "image_url": "/static/img/products/acc_004.jpg",
    },
    {
        "name": "Tattu Plus 12S 22000mAh",
        "sku": "BAT-004",
        "description": "Heavy-duty 44.4V 25C battery for commercial drones with smart BMS and XT90S connector.",
        "price": 599.00,
        "stock": 35,
        "category": "Batteries",
        "image_url": "/static/img/products/bat_004.jpg",
    },
    {
        "name": "DJI FlyCart 30 Frame Kit",
        "sku": "FRM-004",
        "description": "Industrial delivery drone frame with dual payload bays and 30kg max cargo capacity.",
        "price": 8999.00,
        "stock": 8,
        "category": "Frames",
        "image_url": "/static/img/products/frm_004.jpg",
    },
    {
        "name": "Flame 80A HV ESC",
        "sku": "ESC-002",
        "description": "High-voltage 12S capable ESC with FOC control and active cooling for heavy-lift platforms.",
        "price": 149.00,
        "stock": 100,
        "category": "Motors & ESCs",
        "image_url": "/static/img/products/esc_002.jpg",
    },
]

CATEGORY_THEMES = {
    "Complete Drones": {
        "start": "#0f4c81",
        "end": "#62d0ff",
        "accent": "#dff8ff",
        "label": "AIRFRAME",
        "shape": "drone",
    },
    "Frames": {
        "start": "#46327e",
        "end": "#8dd4ff",
        "accent": "#f0f3ff",
        "label": "FRAME",
        "shape": "frame",
    },
    "Motors & ESCs": {
        "start": "#7a2c44",
        "end": "#ff8a63",
        "accent": "#fff0e8",
        "label": "POWERTRAIN",
        "shape": "motor",
    },
    "Flight Controllers": {
        "start": "#1b5e3f",
        "end": "#8fe3a4",
        "accent": "#ecfff1",
        "label": "AUTOPILOT",
        "shape": "chip",
    },
    "Cameras & Gimbals": {
        "start": "#614124",
        "end": "#ffd07a",
        "accent": "#fff7e6",
        "label": "PAYLOAD",
        "shape": "camera",
    },
    "Batteries": {
        "start": "#114a5d",
        "end": "#8cf1d4",
        "accent": "#edfffa",
        "label": "ENERGY",
        "shape": "battery",
    },
    "Propellers": {
        "start": "#334155",
        "end": "#cbd5f5",
        "accent": "#f7f9ff",
        "label": "LIFT",
        "shape": "prop",
    },
    "FPV Gear": {
        "start": "#69264d",
        "end": "#ffa2ce",
        "accent": "#fff0f8",
        "label": "LINK",
        "shape": "visor",
    },
    "Accessories": {
        "start": "#5c3d0a",
        "end": "#ffd36f",
        "accent": "#fff7de",
        "label": "KIT",
        "shape": "case",
    },
}


def _theme_for(category: str) -> dict[str, str]:
    return CATEGORY_THEMES.get(
        category,
        {
            "start": "#12304d",
            "end": "#7ed9ff",
            "accent": "#effbff",
            "label": "OCTO",
            "shape": "grid",
        },
    )


def _shape_svg(shape: str, accent: str) -> str:
    if shape == "drone":
        return (
            f"<circle cx='76' cy='78' r='16' fill='none' stroke='{accent}' stroke-width='6'/>"
            f"<circle cx='244' cy='78' r='16' fill='none' stroke='{accent}' stroke-width='6'/>"
            f"<circle cx='76' cy='206' r='16' fill='none' stroke='{accent}' stroke-width='6'/>"
            f"<circle cx='244' cy='206' r='16' fill='none' stroke='{accent}' stroke-width='6'/>"
            f"<rect x='118' y='96' width='84' height='92' rx='18' fill='none' stroke='{accent}' stroke-width='6'/>"
            f"<path d='M92 92 L128 110 M228 92 L192 110 M92 192 L128 174 M228 192 L192 174' stroke='{accent}' stroke-width='6' stroke-linecap='round'/>"
        )
    if shape == "frame":
        return (
            f"<path d='M84 82 L236 82 L210 204 L110 204 Z' fill='none' stroke='{accent}' stroke-width='7' stroke-linejoin='round'/>"
            f"<path d='M126 82 L110 204 M194 82 L210 204 M92 138 L228 138' stroke='{accent}' stroke-width='5' opacity='0.8'/>"
        )
    if shape == "motor":
        return (
            f"<circle cx='160' cy='142' r='54' fill='none' stroke='{accent}' stroke-width='8'/>"
            f"<circle cx='160' cy='142' r='18' fill='{accent}' opacity='0.8'/>"
            f"<path d='M160 70 L176 118 L232 126 L188 156 L202 212 L160 182 L118 212 L132 156 L88 126 L144 118 Z' fill='none' stroke='{accent}' stroke-width='6' stroke-linejoin='round'/>"
        )
    if shape == "chip":
        return (
            f"<rect x='104' y='86' width='112' height='112' rx='18' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M132 86 V58 M160 86 V52 M188 86 V58 M216 114 H244 M216 142 H252 M216 170 H244 M132 198 V226 M160 198 V232 M188 198 V226 M104 114 H76 M104 142 H68 M104 170 H76' stroke='{accent}' stroke-width='5' stroke-linecap='round'/>"
            f"<path d='M132 114 H188 V170 H132 Z' fill='none' stroke='{accent}' stroke-width='5'/>"
        )
    if shape == "camera":
        return (
            f"<rect x='86' y='98' width='148' height='90' rx='18' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<circle cx='160' cy='143' r='28' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M110 98 L132 78 H188 L210 98' fill='none' stroke='{accent}' stroke-width='7' stroke-linejoin='round'/>"
            f"<path d='M160 188 V220 M136 220 H184' stroke='{accent}' stroke-width='6' stroke-linecap='round'/>"
        )
    if shape == "battery":
        return (
            f"<rect x='98' y='90' width='124' height='108' rx='16' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<rect x='138' y='72' width='44' height='18' rx='6' fill='none' stroke='{accent}' stroke-width='6'/>"
            f"<path d='M154 114 L132 154 H162 L148 188 L188 138 H158 L172 114 Z' fill='{accent}' opacity='0.95'/>"
        )
    if shape == "prop":
        return (
            f"<circle cx='160' cy='142' r='12' fill='{accent}' opacity='0.9'/>"
            f"<path d='M160 130 C182 96 222 92 236 112 C216 132 186 144 160 142 Z' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M172 142 C208 160 220 198 204 216 C180 204 164 176 160 142 Z' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M160 154 C138 188 98 192 84 172 C104 152 134 140 160 142 Z' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M148 142 C112 124 100 86 116 68 C140 80 156 108 160 142 Z' fill='none' stroke='{accent}' stroke-width='7'/>"
        )
    if shape == "visor":
        return (
            f"<path d='M88 130 C104 92 216 92 232 130 V166 C214 194 106 194 88 166 Z' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M104 134 H216' stroke='{accent}' stroke-width='6' opacity='0.8'/>"
            f"<path d='M128 186 L118 220 M192 186 L202 220' stroke='{accent}' stroke-width='6' stroke-linecap='round'/>"
        )
    if shape == "case":
        return (
            f"<rect x='92' y='92' width='136' height='104' rx='18' fill='none' stroke='{accent}' stroke-width='7'/>"
            f"<path d='M128 92 V70 H192 V92' fill='none' stroke='{accent}' stroke-width='7' stroke-linecap='round'/>"
            f"<path d='M126 138 H194 M160 112 V164' stroke='{accent}' stroke-width='6' stroke-linecap='round' opacity='0.8'/>"
        )
    return (
        f"<path d='M94 92 H226 V194 H94 Z M126 92 V194 M160 92 V194 M194 92 V194 M94 126 H226 M94 160 H226' "
        f"fill='none' stroke='{accent}' stroke-width='6' opacity='0.8'/>"
    )


def product_art_data_uri(product: dict[str, Any]) -> str:
    theme = _theme_for(product.get("category", ""))
    title = html.escape(product.get("name", "OCTO Product"))
    sku = html.escape(product.get("sku", "SKU"))
    category = html.escape(product.get("category", "Drone Tech"))
    price = float(product.get("price", 0))
    stock = int(product.get("stock", 0) or 0)
    badge = "READY" if stock > 20 else "LOW STOCK" if stock > 0 else "PREORDER"
    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 320 240" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="{theme['start']}"/>
      <stop offset="100%" stop-color="{theme['end']}"/>
    </linearGradient>
    <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M20 0H0V20" fill="none" stroke="rgba(255,255,255,0.09)" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="320" height="240" rx="26" fill="url(#bg)"/>
  <rect width="320" height="240" rx="26" fill="url(#grid)"/>
  <rect x="18" y="18" width="284" height="204" rx="20" fill="rgba(8,18,30,0.16)" stroke="rgba(255,255,255,0.12)"/>
  <text x="34" y="42" fill="{theme['accent']}" font-size="14" font-family="Arial, sans-serif" letter-spacing="2">{theme['label']}</text>
  {_shape_svg(theme['shape'], theme['accent'])}
  <rect x="34" y="172" width="108" height="28" rx="14" fill="rgba(8,18,30,0.22)"/>
  <text x="88" y="190" text-anchor="middle" fill="{theme['accent']}" font-size="11" font-family="Arial, sans-serif" letter-spacing="1.4">{badge}</text>
  <text x="34" y="208" fill="white" font-size="16" font-family="Arial, sans-serif" font-weight="700">{title[:30]}</text>
  <text x="34" y="225" fill="rgba(255,255,255,0.78)" font-size="12" font-family="Arial, sans-serif">{category} | {sku}</text>
  <text x="286" y="206" text-anchor="end" fill="white" font-size="24" font-family="Arial, sans-serif" font-weight="700">${price:,.0f}</text>
</svg>
""".strip()
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def product_specs(product: dict[str, Any]) -> list[dict[str, str]]:
    description = product.get("description", "") or ""
    specs: list[dict[str, str]] = [
        {"label": "Category", "value": product.get("category", "Drone Tech")},
        {"label": "SKU", "value": product.get("sku", "N/A")},
        {"label": "Availability", "value": f"{int(product.get('stock', 0) or 0)} units in ATP"},
    ]
    patterns = [
        ("Flight", r"(\d+\s?min(?:ute)?s?(?:\sflight|\sendurance)?)"),
        ("Camera", r"(\d+K(?: HDR)? camera|\d+MP sensor|LiDAR \+ 4K camera)"),
        ("Range", r"(\d+\s?km range|\d+\s?km reach|up to \d+\s?km range)"),
        ("Payload", r"(\d+\s?kg payload|\d+lb payload)"),
        ("Power", r"(\d+S\s\d+mAh|\d+Wh portable power station)"),
    ]
    found = 0
    for label, pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            specs.append({"label": label, "value": match.group(1)})
            found += 1
    if found == 0:
        specs.append({"label": "Technical note", "value": "Grounded from ATP catalog description."})
    return specs[:6]


def product_rating(product: dict[str, Any]) -> float:
    base = 4.0 + ((int(product.get("id", 0) or 0) + int(product.get("stock", 0) or 0)) % 8) / 10
    return round(min(base, 4.9), 1)


def product_summary(product: dict[str, Any]) -> str:
    specs = ", ".join(f"{item['label']}: {item['value']}" for item in product_specs(product)[1:4])
    return (
        f"{product.get('name')} is listed in category {product.get('category')} at "
        f"${float(product.get('price', 0)):,.2f}. {product.get('description', '')} {specs}".strip()
    )


def enrich_product(product: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(product)
    enriched["image_url"] = product.get("image_url") or product_art_data_uri(product)
    enriched["rating"] = product_rating(product)
    enriched["specs"] = product_specs(product)
    enriched["summary"] = product_summary(product)
    enriched["support_tier"] = "Mission Ready" if float(product.get("price", 0) or 0) >= 5000 else "Field Ready"
    enriched["inventory_badge"] = (
        "In Stock" if int(product.get("stock", 0) or 0) > 20
        else "Low Stock" if int(product.get("stock", 0) or 0) > 0
        else "Backorder"
    )
    return enriched


def build_grounding_documents(products: list[dict[str, Any]]) -> list[dict[str, str]]:
    documents = []
    for product in products[:8]:
        specs = "; ".join(f"{item['label']}: {item['value']}" for item in product_specs(product)[1:5])
        documents.append(
            {
                "title": product.get("name", "Drone Product"),
                "snippet": product.get("description", ""),
                "category": product.get("category", ""),
                "details": specs,
            }
        )
    return documents


def fallback_product_answer(message: str, products: list[dict[str, Any]]) -> str:
    lowered = (message or "").lower()
    if not products:
        return "The OCTO drone advisor could not find matching products in ATP. Check the catalog filters and try again."

    ranked = sorted(
        products,
        key=lambda product: sum(
            3
            for token in re.findall(r"[a-z0-9\+\-]+", lowered)
            if token and token in f"{product.get('name','')} {product.get('description','')} {product.get('category','')}".lower()
        ),
        reverse=True,
    )
    best = ranked[0]
    specs = product_specs(best)
    lines = [
        f"{best.get('name')} is the closest ATP match.",
        f"Category: {best.get('category')}. Price: ${float(best.get('price', 0)):,.2f}.",
        best.get("description", ""),
    ]
    if len(specs) > 1:
        lines.append("Key details: " + "; ".join(f"{item['label']} {item['value']}" for item in specs[1:4]) + ".")
    if "compare" in lowered and len(ranked) > 1:
        alt = ranked[1]
        lines.append(
            f"Alternative option: {alt.get('name')} at ${float(alt.get('price', 0)):,.2f} for {alt.get('category')} workloads."
        )
    if "battery" in lowered or "power" in lowered:
        lines.append("For endurance planning, pair the aircraft with a spare battery set and a field charger from the Batteries catalog.")
    if "mapping" in lowered or "survey" in lowered:
        lines.append("For mapping missions, prioritize RTK-capable platforms, long endurance, and high-resolution payloads.")
    return " ".join(part for part in lines if part)
