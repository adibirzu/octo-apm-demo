"""Build private demo facilitator screenshots and PDF.

The generated guide uses placeholder hostnames, reserved IP examples, and
synthetic identities only. It intentionally does not read deployment secret
files; operators load credentials locally when they run the documented
commands.

Use ``--live`` after running ``capture_live_screenshots.mjs`` to build the
private operator PDF with redacted screenshots from the live deployment.
"""

from __future__ import annotations

import argparse
import html
import os
import shutil
import subprocess
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, ListFlowable, ListItem, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = ROOT / "tmp" / "demo-guide"
SCREENSHOT_DIR = ROOT / "site" / "assets" / "demo" / "screenshots"
LIVE_SCREENSHOT_DIR = ROOT / "site" / "assets" / "demo" / "private-live"
OCI_CONSOLE_SCREENSHOT_DIR = ROOT / "site" / "assets" / "demo" / "private-oci-console"
SITE_PDF = ROOT / "site" / "assets" / "demo" / "octo-private-demo-facilitator-guide.pdf"
OUTPUT_PDF = ROOT / "output" / "pdf" / "octo-private-demo-facilitator-guide.pdf"


BASE_STYLE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #101419;
    --panel: #182029;
    --panel-2: #202b36;
    --line: #334252;
    --text: #edf3f7;
    --muted: #9fb0bf;
    --teal: #67d2d0;
    --amber: #f6b85f;
    --red: #ef6b73;
    --green: #71d99e;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    width: 1440px;
    min-height: 900px;
    font-family: Inter, Arial, sans-serif;
    color: var(--text);
    background: linear-gradient(135deg, #11161d 0%, #19232d 55%, #11161d 100%);
  }
  .topbar, .sidebar {
    background: rgba(24, 32, 41, 0.96);
    border: 1px solid var(--line);
  }
  .topbar {
    margin: 22px auto 18px;
    width: 1320px;
    min-height: 78px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    border-radius: 16px;
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .logo {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: linear-gradient(135deg, var(--teal), #6c86ff);
  }
  h1, h2, h3 { margin: 0; letter-spacing: 0; }
  h1 { font-size: 30px; }
  h2 { font-size: 22px; }
  h3 { font-size: 17px; }
  p { color: var(--muted); line-height: 1.5; margin: 6px 0 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-flex;
    align-items: center;
    border: 1px solid var(--line);
    background: rgba(255,255,255,0.04);
    border-radius: 999px;
    padding: 8px 12px;
    color: var(--muted);
    font-size: 13px;
  }
  .chip.ok { color: var(--green); border-color: rgba(113,217,158,0.45); }
  .chip.warn { color: var(--amber); border-color: rgba(246,184,95,0.45); }
  .chip.bad { color: var(--red); border-color: rgba(239,107,115,0.45); }
  .layout { width: 1320px; margin: 0 auto; display: grid; grid-template-columns: 1fr 360px; gap: 18px; }
  .crm-layout { width: 1320px; margin: 0 auto; display: grid; grid-template-columns: 260px 1fr; gap: 18px; }
  .sidebar { border-radius: 16px; padding: 20px; min-height: 780px; }
  .nav { display: grid; gap: 8px; margin-top: 22px; }
  .nav div { padding: 11px 12px; border-radius: 10px; color: var(--muted); }
  .nav div.active { background: rgba(103,210,208,0.12); color: var(--teal); }
  .grid { display: grid; gap: 16px; }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  .panel, .card {
    background: rgba(24, 32, 41, 0.96);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 18px;
    box-shadow: 0 18px 50px rgba(0,0,0,0.22);
  }
  .product { min-height: 260px; display: grid; grid-template-rows: 116px auto; overflow: hidden; padding: 0; }
  .product-img { background: linear-gradient(135deg, #273646, #3e5867); border-bottom: 1px solid var(--line); }
  .product-body { padding: 16px; }
  .price { color: var(--teal); font-weight: 700; font-size: 22px; margin-top: 10px; }
  .btn {
    display: inline-flex;
    justify-content: center;
    align-items: center;
    padding: 11px 14px;
    border-radius: 9px;
    background: rgba(103,210,208,0.14);
    border: 1px solid rgba(103,210,208,0.56);
    color: var(--teal);
    font-weight: 700;
    font-size: 13px;
  }
  .btn.red { color: var(--red); border-color: rgba(239,107,115,0.56); background: rgba(239,107,115,0.12); }
  .btn.amber { color: var(--amber); border-color: rgba(246,184,95,0.56); background: rgba(246,184,95,0.12); }
  input, textarea, select {
    width: 100%;
    border: 1px solid var(--line);
    background: var(--panel-2);
    color: var(--text);
    border-radius: 8px;
    padding: 10px 12px;
    font: inherit;
  }
  .form { display: grid; gap: 10px; }
  .row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #0d1117;
    border: 1px solid #2f3b49;
    border-radius: 10px;
    padding: 14px;
    color: #c9d7e2;
    min-height: 84px;
    white-space: pre-wrap;
  }
  .timeline { display: grid; gap: 10px; }
  .timeline-item { display: grid; grid-template-columns: 140px 1fr 120px; gap: 12px; align-items: center; padding: 12px; border-radius: 10px; background: rgba(255,255,255,0.035); border: 1px solid var(--line); }
</style>
</head>
<body>
__BODY__
</body>
</html>
"""


def write_html(name: str, body: str) -> Path:
    path = TMP_DIR / f"{name}.html"
    path.write_text(BASE_STYLE.replace("__BODY__", body), encoding="utf-8")
    return path


def build_html_pages() -> dict[str, Path]:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    pages = {
        "shop-checkout": """
<div class="topbar">
  <div class="brand"><div class="logo"></div><div><h1>OCTO Drone Commerce</h1><p>Shop journey with synthetic RUM identity</p></div></div>
  <div class="chips"><span class="chip ok">APM enabled</span><span class="chip ok">RUM user: maya.ionescu@apex.example.test</span><span class="chip">ATP orders</span></div>
</div>
<div class="layout">
  <main class="grid">
    <section class="panel row"><div><h2>Drone Shop</h2><p>Open the shop, add drones, and submit checkout with dummy payment data.</p></div><div class="chips"><span class="chip">Complete Drones</span><span class="chip">Flight Controllers</span><span class="chip">Support</span></div></section>
    <section class="grid grid-3">
      <article class="product card"><div class="product-img"></div><div class="product-body"><h3>Skydio X10 Fleet Kit</h3><p>Autonomous drone package for inspection teams.</p><div class="price">$10,999</div><div class="btn">Add to Cart</div></div></article>
      <article class="product card"><div class="product-img"></div><div class="product-body"><h3>Thermal Payload Bundle</h3><p>Payload and calibration package for field response.</p><div class="price">$4,499</div><div class="btn">Add to Cart</div></div></article>
      <article class="product card"><div class="product-img"></div><div class="product-body"><h3>BVLOS Training Service</h3><p>Training service that creates support traces.</p><div class="price">$4,500</div><div class="btn">Add Service</div></div></article>
    </section>
  </main>
  <aside class="panel">
    <div class="row"><h2>Cart & Checkout</h2><span class="chip ok">2 items</span></div>
    <div class="code">Skydio X10 Fleet Kit x1\nThermal Payload Bundle x1\nTrace headers: traceparent + X-Run-Id</div>
    <form class="form">
      <input value="Maya Ionescu">
      <input value="maya.ionescu@apex.example.test">
      <input value="Apex Field Services">
      <textarea>Synthetic operations address</textarea>
      <select><option>Credit Card</option></select>
      <div class="btn">Place Order</div>
    </form>
  </aside>
</div>
""",
        "admin-simulation": """
<div class="crm-layout">
  <aside class="sidebar">
    <div class="brand"><div class="logo"></div><div><h2>Enterprise CRM</h2><p>Simulation lab</p></div></div>
    <div class="nav"><div>Dashboard</div><div>Customers</div><div>Orders</div><div class="active">Simulation</div><div>360 Monitoring</div></div>
  </aside>
  <main class="grid">
    <section class="panel row"><div><h1>Simulation</h1><p>Generate buyer, Java app-server, payment, attack, and OSQuery evidence.</p></div><div class="chips"><span class="chip ok">Shop linked</span><span class="chip ok">Java APM</span><span class="chip warn">Log Analytics route</span></div></section>
    <section class="grid grid-2">
      <div class="card"><h2>Demo Storyboard</h2><p>Shop -> Payment -> Support -> Java APM</p><div class="grid grid-2"><input value="Field operations buyer"><input value="4242424242424242"><input value="198.51.100.42"><input value="2"></div><br><div class="btn">Run Story</div><div class="code">storyboard ready\nexpected: order, ticket, payment, Java spans</div></div>
      <div class="card"><h2>Synthetic Users</h2><p>Populate APM Users and ATP orders.</p><div class="grid grid-2"><input value="apex.example.test"><input value="12 users"><input value="6 orders"><input value="delete older than 7d"></div><br><div class="btn">Generate Users</div><div class="code">apmrum.username set from local storage\norders source=synthetic-user-cron</div></div>
      <div class="card"><h2>Attack Lab</h2><p>MITRE, OSQuery, app logs, spans.</p><div class="grid grid-2"><input value="203.0.113.77"><select><option>C2 Callback 503</option></select></div><br><div class="btn red">Generate Attack</div><div class="code">security.attack.id=attack-&lt;id&gt;\nmitre.technique_id=T1190,T1059,T1046...</div></div>
      <div class="card"><h2>Availability Monitoring</h2><p>Global readiness checks.</p><div class="chips"><span class="chip">Phoenix</span><span class="chip">Ashburn</span><span class="chip">Frankfurt</span><span class="chip">Tokyo</span></div><br><div class="btn amber">Render CLI Command</div></div>
    </section>
  </main>
</div>
""",
        "attack-investigation": """
<div class="topbar">
  <div class="brand"><div class="logo"></div><div><h1>Compromise Investigation</h1><p>Alert pivot across APM, Log Analytics, OSQuery, and metrics</p></div></div>
  <div class="chips"><span class="chip bad">Critical alert</span><span class="chip">attack-&lt;id&gt;</span><span class="chip">trace-&lt;id&gt;</span></div>
</div>
<div class="layout">
  <main class="grid">
    <section class="panel">
      <h2>Attack Timeline</h2>
      <div class="timeline">
        <div class="timeline-item"><span class="chip bad">Initial access</span><div>Exploit public app path, source 203.0.113.77 to shop.example.test</div><span>T1190</span></div>
        <div class="timeline-item"><span class="chip warn">Execution</span><div>LOTL shell and Java sidecar error spans linked by oracleApmTraceId</div><span>T1059</span></div>
        <div class="timeline-item"><span class="chip warn">Discovery</span><div>OSQuery detects unexpected listeners and recent processes</div><span>T1046</span></div>
        <div class="timeline-item"><span class="chip ok">Evidence</span><div>Log Analytics dashboard joins app logs, OSQuery findings, and APM span ids</div><span>Trace/log</span></div>
      </div>
    </section>
    <section class="grid grid-3">
      <div class="card"><h3>APM Trace</h3><p>Open `security.attack.kill_chain`, inspect Java and SQL spans.</p></div>
      <div class="card"><h3>Log Analytics</h3><p>Filter `security.attack.id` and `oracleApmTraceId`.</p></div>
      <div class="card"><h3>Metrics</h3><p>Confirm CPU, process, JVM, and checkout error spikes.</p></div>
    </section>
  </main>
  <aside class="panel">
    <h2>Operator Verdict</h2>
    <div class="code">Severity: Critical\nStatus: Simulated compromise\nHost evidence: OSQuery exported\nNext action: containment runbook</div>
    <p>Use this as the closing story: alert -> trace -> logs -> host evidence -> dashboard.</p>
  </aside>
</div>
""",
    }
    return {name: write_html(name, body) for name, body in pages.items()}


def screenshot_pages(pages: dict[str, Path]) -> dict[str, Path]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    screenshots = {}
    for name, html_path in pages.items():
        out = SCREENSHOT_DIR / f"{name}.png"
        subprocess.run(
            [
                "npx",
                "--yes",
                "playwright",
                "screenshot",
                "--viewport-size=1440,900",
                f"file://{html_path}",
                str(out),
            ],
            cwd=ROOT,
            check=True,
        )
        screenshots[name] = out
    return screenshots


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(text), style)


def bullet_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(paragraph(item, style), bulletColor=colors.HexColor("#2f6f73")) for item in items],
        bulletType="bullet",
        leftIndent=18,
    )


def numbered_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(paragraph(item, style), bulletColor=colors.HexColor("#2f6f73")) for item in items],
        bulletType="1",
        leftIndent=18,
    )


def add_screenshot(story: list, path: Path, width: float = 6.6 * inch, max_height: float = 8.3 * inch) -> None:
    image_width, image_height = ImageReader(str(path)).getSize()
    render_height = width * image_height / image_width
    if render_height > max_height:
        render_height = max_height
        width = render_height * image_width / image_height
    story.append(Image(str(path), width=width, height=render_height))
    story.append(Spacer(1, 0.16 * inch))


def build_pdf(screenshots: dict[str, Path]) -> None:
    SITE_PDF.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="GuideTitle", parent=styles["Title"], fontSize=24, leading=30, textColor=colors.HexColor("#1f2a33")))
    styles.add(ParagraphStyle(name="GuideHeading", parent=styles["Heading2"], fontSize=15, leading=18, spaceBefore=12, textColor=colors.HexColor("#1f2a33")))
    body = ParagraphStyle(name="GuideBody", parent=styles["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#27323a"))
    small = ParagraphStyle(name="GuideSmall", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#4e5d68"))
    code = ParagraphStyle(name="GuideCode", parent=styles["Code"], fontSize=7.8, leading=10, backColor=colors.HexColor("#f2f5f7"), borderColor=colors.HexColor("#d6dee5"), borderWidth=0.3, borderPadding=5)

    story: list = [
        Paragraph("OCTO Private Demo Facilitator Guide", styles["GuideTitle"]),
        paragraph("Safe delivery guide for the private observability, RUM, synthetic users, and attack-lab demo. All values are placeholders; load real credentials only from ignored deployment files on the operator machine.", body),
        Spacer(1, 0.18 * inch),
        Table(
            [
                ["Shop", "https://shop.example.test"],
                ["Admin", "https://admin.example.test"],
                ["Synthetic domain", "apex.example.test"],
                ["Credentials", "credentials/<profile>/app-secrets.env (not printed in this guide)"],
            ],
            colWidths=[1.8 * inch, 4.8 * inch],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f1f1")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bcc8cf")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
        Spacer(1, 0.2 * inch),
        Paragraph("Demo Story", styles["GuideHeading"]),
        bullet_list([
            "Open the shop and confirm the RUM pill is enabled.",
            "Run the browser journey or use the admin Synthetic Users card so APM Users receives distinct fictional users.",
            "Add drones to the cart, enter dummy payment data, and place an order.",
            "Use the support/service flow so logs, payment spans, Java spans, and SQL spans share one trace.",
            "Generate the attack lab and pivot from alert to APM trace, Log Analytics, OSQuery findings, and host/JVM metrics.",
        ], body),
        Paragraph("Frontend Step 1 - Shop Checkout", styles["GuideHeading"]),
    ]
    add_screenshot(story, screenshots["shop-checkout"])
    story.extend([
        PageBreak(),
        Paragraph("Frontend Step 2 - Admin Simulation Lab", styles["GuideHeading"]),
    ])
    add_screenshot(story, screenshots["admin-simulation"])
    story.extend([
        PageBreak(),
        Paragraph("Backend Prep", styles["GuideHeading"]),
        paragraph("Run commands from the repository root. The commands below intentionally use placeholders and do not expose secret values.", body),
        Preformatted("set -a; . credentials/<profile>/app-secrets.env; set +a\ncurl -k -fsS --resolve shop.example.test:443:203.0.113.10 \\\n  -H 'Content-Type: application/json' \\\n  -H \"X-Internal-Service-Key: ${INTERNAL_SERVICE_KEY}\" \\\n  -X POST https://shop.example.test/api/synthetic/users/run \\\n  -d '{\"domain\":\"apex.example.test\",\"count\":12,\"order_count\":6,\"delete_after_days\":7}'", code),
        Paragraph("Attack Alert Use Case", styles["GuideHeading"]),
        paragraph("The user receives a critical alert for possible compromise. The demoer opens the returned trace id in APM, then uses the attack id in Log Analytics saved searches. OSQuery results are exported to OCI Logging and routed to Log Analytics when the connector is available.", body),
    ])
    add_screenshot(story, screenshots["attack-investigation"])
    story.extend([
        Paragraph("Expected Evidence", styles["GuideHeading"]),
        bullet_list([
            "APM Users shows synthetic users from the configured domain.",
            "APM Trace Explorer shows shop, CRM, Java app-server, payment, and SQL spans.",
            "App logs carry oracleApmTraceId and oracleApmSpanId for Log Analytics drilldown.",
            "Attack logs carry security.attack.id, mitre.technique_id, client.address, server.address, osquery.query, and host fields.",
            "Metrics show request, error, JVM/app-server, and VM/resource spikes for the scenario window.",
        ], body),
        Spacer(1, 0.1 * inch),
        paragraph("Keep this branch and generated guide private unless placeholders are reviewed again and deployment credentials are excluded.", small),
    ])

    doc = SimpleDocTemplate(str(SITE_PDF), pagesize=letter, rightMargin=0.55 * inch, leftMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.55 * inch)
    doc.build(story)
    shutil.copyfile(SITE_PDF, OUTPUT_PDF)


def collect_live_screenshots() -> dict[str, Path]:
    mapping = {
        "shop-catalog": "shop-catalog-live.png",
        "shop-checkout": "shop-checkout-ready-live.png",
        "shop-order": "shop-order-complete-live.png",
        "shop-support": "shop-support-ticket-submitted-live.png",
        "admin-simulation": "admin-simulation-live.png",
        "admin-java": "admin-java-apm-health-live.png",
        "admin-storyboard": "admin-storyboard-output-live.png",
        "admin-attack": "admin-attack-lab-output-live.png",
        "admin-availability": "admin-availability-plan-live.png",
        "admin-monitoring": "admin-360-monitoring-live.png",
    }
    optional_mapping = {
        "admin-synthetic-users": "admin-synthetic-users-output-live.png",
    }
    console_mapping = {
        "oci-apm-trace": "oci-apm-trace-explorer-live.png",
        "oci-apm-rum": "oci-apm-rum-live.png",
        "oci-logging": "oci-logging-logs-live.png",
        "oci-connector": "oci-service-connector-hub-live.png",
        "oci-log-analytics": "oci-log-analytics-explorer-live.png",
        "oci-cloud-guard": "oci-cloud-guard-problems-live.png",
        "oci-monitoring": "oci-monitoring-alarms-live.png",
        "oci-stack-monitoring": "oci-stack-monitoring-resources-live.png",
        "oci-availability": "oci-availability-monitoring-live.png",
    }
    screenshots = {key: LIVE_SCREENSHOT_DIR / name for key, name in mapping.items()}
    for key, name in optional_mapping.items():
        optional_path = LIVE_SCREENSHOT_DIR / name
        if optional_path.exists():
            screenshots[key] = optional_path
    screenshots.update({key: OCI_CONSOLE_SCREENSHOT_DIR / name for key, name in console_mapping.items()})
    missing = [str(path.relative_to(ROOT)) for path in screenshots.values() if not path.exists()]
    if missing:
        raise SystemExit(
            "Missing live screenshots. Run `set -a; . credentials/<profile>/app-secrets.env; "
            "set +a; node tools/demo-guide/capture_live_screenshots.mjs` first.\n"
            + "\n".join(f"- {item}" for item in missing)
        )
    return screenshots


def build_live_pdf(screenshots: dict[str, Path]) -> None:
    shop_url = os.getenv("OCTO_LIVE_SHOP_URL", "https://shop.example.test")
    admin_url = os.getenv("OCTO_LIVE_ADMIN_URL", "https://admin.example.test")
    credential_source = os.getenv("OCTO_LIVE_CREDENTIAL_SOURCE", "credentials/<profile>/app-secrets.env")

    SITE_PDF.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="GuideTitle", parent=styles["Title"], fontSize=24, leading=30, textColor=colors.HexColor("#1f2a33")))
    styles.add(ParagraphStyle(name="GuideHeading", parent=styles["Heading2"], fontSize=15, leading=18, spaceBefore=12, textColor=colors.HexColor("#1f2a33")))
    body = ParagraphStyle(name="GuideBody", parent=styles["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#27323a"))
    small = ParagraphStyle(name="GuideSmall", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#4e5d68"))
    code = ParagraphStyle(name="GuideCode", parent=styles["Code"], fontSize=7.8, leading=10, backColor=colors.HexColor("#f2f5f7"), borderColor=colors.HexColor("#d6dee5"), borderWidth=0.3, borderPadding=5)

    story: list = [
        Paragraph("OCTO Private Live Demo Facilitator Guide", styles["GuideTitle"]),
        paragraph("Private delivery guide with live screenshots captured from the current deployment. Screenshots are redacted where the UI shows OCIDs or other deployment identifiers. Keep this PDF out of public branches and public documentation sites.", body),
        Spacer(1, 0.18 * inch),
        Table(
            [
                ["Shop", shop_url],
                ["Admin", admin_url],
                ["Synthetic identity", "Fictional users only; no real user credentials in screenshots"],
                ["Credential source", f"{credential_source} (ignored, never printed)"],
            ],
            colWidths=[1.8 * inch, 4.8 * inch],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f1f1")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bcc8cf")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
        Spacer(1, 0.2 * inch),
        Paragraph("Lab 1 - Buyer Frontend Flow", styles["GuideHeading"]),
        numbered_list([
            f"Open {shop_url}/shop and confirm the live catalog renders with ATP, APM, and CRM sync indicators.",
            "Add two drone products to the cart. Use fictional buyer details only.",
            "Submit checkout once with dummy payment data. Capture the returned order id for the investigation story.",
            f"Open {shop_url}/services and submit a support ticket for the same fictional buyer.",
            "Keep the browser tab active so RUM records the page views, user actions, and session attributes.",
        ], body),
    ]
    add_screenshot(story, screenshots["shop-catalog"], width=6.6 * inch, max_height=5.0 * inch)
    add_screenshot(story, screenshots["shop-checkout"], width=3.0 * inch, max_height=4.8 * inch)
    add_screenshot(story, screenshots["shop-order"], width=3.0 * inch, max_height=4.8 * inch)
    add_screenshot(story, screenshots["shop-support"], width=6.6 * inch, max_height=4.6 * inch)

    story.extend([
        PageBreak(),
        Paragraph("Lab 2 - Admin Simulation Flow", styles["GuideHeading"]),
        numbered_list([
            f"Open {admin_url}/login and sign in with the demo admin account from the ignored deployment credential file.",
            f"Open {admin_url}/settings and verify the Java APM, Storyboard, Synthetic Users, Attack Lab, Availability, and 360 Monitoring controls that are visible in the current build.",
            "Run Java Health to validate the small Java app-server component instrumented with the OCI APM Java agent.",
            "Run Demo Storyboard to link shop, dummy payment, support ticket, Java app-server, ATP SQL, and structured logs.",
            "Run Synthetic Users when the card is visible, or use the configured VM timer, so APM Users receives multiple fictional corporate identities.",
            "Run Attack Lab and copy the returned attack id and trace id.",
            "Use the Availability Monitoring card to explain the global monitor plan for both live domains.",
        ], body),
    ])
    add_screenshot(story, screenshots["admin-simulation"], width=6.6 * inch, max_height=7.3 * inch)
    add_screenshot(story, screenshots["admin-java"], width=4.7 * inch, max_height=4.3 * inch)
    add_screenshot(story, screenshots["admin-storyboard"], width=4.7 * inch, max_height=4.3 * inch)
    if "admin-synthetic-users" in screenshots:
        add_screenshot(story, screenshots["admin-synthetic-users"], width=4.7 * inch, max_height=4.3 * inch)
    add_screenshot(story, screenshots["admin-attack"], width=4.7 * inch, max_height=4.3 * inch)
    add_screenshot(story, screenshots["admin-availability"], width=4.7 * inch, max_height=3.5 * inch)

    story.extend([
        PageBreak(),
        Paragraph("Lab 3 - OCI Console Threat Hunting Workflow", styles["GuideHeading"]),
        paragraph("Start from the Admin Attack Lab output. Copy the returned attack id and trace id, then pivot through the OCI Console services below. The same values also drive the Log Analytics saved searches shipped in deploy/oci/log_analytics/searches/.", body),
        numbered_list([
            "Monitoring: open Alarm Status and Metrics Explorer for the scenario window; verify VM CPU, memory, network, app error, and checkout latency spikes.",
            "APM Trace Explorer: search by trace id, then inspect Shop, CRM, Java app-server, payment, SQL, and attack-lab spans. Add attributes for workflow.id, security.attack.id, mitre.technique_id, db.statement, DbOracleSqlId, and oracleApmTraceId.",
            "APM Users: verify RUM user sessions for fictional synthetic identities and confirm browser actions align with the checkout/support timeline.",
            "OCI Logging and Service Connector Hub: confirm app, stdout, OS, WAF, Cloud Guard raw, and Cloud Guard query result logs are flowing into Log Analytics.",
            "Log Analytics: run attack-lab-trace-timeline.sql, attack-lab-detections.sql, and osquery-attack-findings.sql using the attack id and trace id.",
            "Cloud Guard and Instance Security: review Problems, detector recipes, and OSQuery results, then export completed query results into OCI Logging for the same attack id.",
            "Stack Monitoring, Database Management, and Operations Insights: pivot from the application trace to host, ATP, and SQL performance signals for the same time range.",
            "Availability Monitoring: check global readiness monitors for both domains and compare vantage point failures with LB/app logs.",
        ], body),
        Paragraph("In-App Console Map", styles["GuideHeading"]),
    ])
    add_screenshot(story, screenshots["admin-monitoring"], width=6.6 * inch, max_height=7.4 * inch)
    story.extend([
        PageBreak(),
        Paragraph("OCI APM Evidence", styles["GuideHeading"]),
        paragraph("Use Trace Explorer as the authoritative request timeline, then use Real User Monitoring to prove the browser-side shop actions in the same time window.", body),
    ])
    add_screenshot(story, screenshots["oci-apm-trace"], width=6.6 * inch, max_height=3.4 * inch)
    add_screenshot(story, screenshots["oci-apm-rum"], width=6.6 * inch, max_height=3.4 * inch)
    story.extend([
        PageBreak(),
        Paragraph("OCI Logs And Log Analytics", styles["GuideHeading"]),
        paragraph("Confirm durable OCI Logging records, Connector Hub routing, and the Log Analytics saved-search workflow for trace and attack ids.", body),
    ])
    add_screenshot(story, screenshots["oci-logging"], width=6.6 * inch, max_height=2.8 * inch)
    add_screenshot(story, screenshots["oci-connector"], width=6.6 * inch, max_height=2.8 * inch)
    add_screenshot(story, screenshots["oci-log-analytics"], width=6.6 * inch, max_height=2.8 * inch)
    story.extend([
        PageBreak(),
        Paragraph("Security, Metrics, And Availability", styles["GuideHeading"]),
        paragraph("Use Cloud Guard for the security finding, Monitoring for alarms and VM metrics, Stack Monitoring for host/app-server context, and Availability Monitoring for global readiness evidence.", body),
    ])
    add_screenshot(story, screenshots["oci-cloud-guard"], width=6.6 * inch, max_height=2.7 * inch)
    add_screenshot(story, screenshots["oci-monitoring"], width=6.6 * inch, max_height=2.7 * inch)
    add_screenshot(story, screenshots["oci-stack-monitoring"], width=6.6 * inch, max_height=2.7 * inch)
    add_screenshot(story, screenshots["oci-availability"], width=6.6 * inch, max_height=2.7 * inch)
    story.extend([
        paragraph("If a control is hidden in the live UI, use the paired VM timer or backend endpoint already configured for the deployment and document the gap before the demo starts.", small),
        paragraph("Keep this branch, screenshots, and generated PDF private. Redact screenshots again if the live UI changes and starts showing OCIDs, tenancy names, private IPs, credentials, or wallet details.", small),
    ])

    doc = SimpleDocTemplate(str(SITE_PDF), pagesize=letter, rightMargin=0.55 * inch, leftMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.55 * inch)
    doc.build(story)
    shutil.copyfile(SITE_PDF, OUTPUT_PDF)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Build PDF from redacted live deployment screenshots.")
    args = parser.parse_args()
    if args.live:
        screenshots = collect_live_screenshots()
        build_live_pdf(screenshots)
    else:
        pages = build_html_pages()
        screenshots = screenshot_pages(pages)
        build_pdf(screenshots)
    print(f"wrote {SITE_PDF.relative_to(ROOT)}")
    print(f"wrote {OUTPUT_PDF.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
