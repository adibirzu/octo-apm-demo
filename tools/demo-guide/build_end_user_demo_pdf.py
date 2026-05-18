"""Build the public end-user OCTO demo PDF.

This guide is safe for the public GitHub Pages site. It uses only placeholder
hostnames, fictional users, dummy payment values, and public OCI navigation
paths. Do not add live domains, IPs, OCIDs, tenancy names, or credentials here.
"""

from __future__ import annotations

import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = ROOT / "site" / "assets" / "demo" / "octo-end-user-demo-guide.pdf"
SCREENSHOT_DIR = ROOT / "site" / "assets" / "demo" / "screenshots"

DEMO_USERS = [
    ("Alex Chen", "alex.chen@apex.example.test", "Fleet operations buyer"),
    ("Maya Ionescu", "maya.ionescu@apex.example.test", "Field services buyer"),
    ("Nora Patel", "nora.patel@apex.example.test", "Energy survey buyer"),
    ("Daniel Rossi", "daniel.rossi@apex.example.test", "Infrastructure buyer"),
    ("Irina Marin", "irina.marin@apex.example.test", "Public safety buyer"),
    ("Samuel Wright", "samuel.wright@apex.example.test", "Logistics buyer"),
    ("Elena Garcia", "elena.garcia@apex.example.test", "Agriculture buyer"),
    ("Noah Kim", "noah.kim@apex.example.test", "Inspection buyer"),
    ("Sofia Andersen", "sofia.andersen@apex.example.test", "Rail systems buyer"),
    ("Matei Popa", "matei.popa@apex.example.test", "Utilities buyer"),
    ("Lina Hoffman", "lina.hoffman@apex.example.test", "Emergency response buyer"),
    ("Omar Saleh", "omar.saleh@apex.example.test", "Maritime buyer"),
]


def make_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="GuideTitle",
            parent=styles["Title"],
            fontSize=23,
            leading=28,
            spaceAfter=8,
            textColor=colors.HexColor("#1f2a33"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideSubtitle",
            parent=styles["BodyText"],
            fontSize=10.5,
            leading=15,
            spaceAfter=10,
            textColor=colors.HexColor("#40515f"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideHeading",
            parent=styles["Heading2"],
            fontSize=15,
            leading=18,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#1f2a33"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideSubheading",
            parent=styles["Heading3"],
            fontSize=11.5,
            leading=14,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor("#2f3d46"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideBody",
            parent=styles["BodyText"],
            fontSize=9.2,
            leading=12.7,
            textColor=colors.HexColor("#27323a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideSmall",
            parent=styles["BodyText"],
            fontSize=7.9,
            leading=10.2,
            textColor=colors.HexColor("#4e5d68"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideCode",
            parent=styles["Code"],
            fontSize=7.6,
            leading=9.8,
            backColor=colors.HexColor("#f2f5f7"),
            borderColor=colors.HexColor("#d6dee5"),
            borderWidth=0.3,
            borderPadding=5,
            textColor=colors.HexColor("#26333d"),
        )
    )
    return styles


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(text), style)


def cell(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(text), style)


def bullet_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(paragraph(item, style), bulletColor=colors.HexColor("#2f6f73")) for item in items],
        bulletType="bullet",
        leftIndent=16,
        bulletFontSize=7,
    )


def numbered_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(paragraph(item, style), bulletColor=colors.HexColor("#2f6f73")) for item in items],
        bulletType="1",
        leftIndent=16,
        bulletFontSize=7,
    )


def styled_table(
    rows: list[list[str]],
    widths: list[float],
    body: ParagraphStyle,
    small: ParagraphStyle,
    header: bool = True,
) -> Table:
    data = []
    for row_index, row in enumerate(rows):
        style = small if row_index == 0 and header else body
        data.append([cell(value, style) for value in row])
    table = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1f1") if header else colors.white),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f2a33")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bcc8cf")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def add_screenshot(story: list, filename: str, width: float = 6.5 * inch, max_height: float = 6.8 * inch) -> None:
    path = SCREENSHOT_DIR / filename
    if not path.exists():
        raise SystemExit(f"Missing screenshot: {path.relative_to(ROOT)}")
    image_width, image_height = ImageReader(str(path)).getSize()
    render_height = width * image_height / image_width
    if render_height > max_height:
        render_height = max_height
        width = render_height * image_width / image_height
    story.append(Image(str(path), width=width, height=render_height))
    story.append(Spacer(1, 0.12 * inch))


def add_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#63707a"))
    canvas.drawString(doc.leftMargin, 0.34 * inch, "OCTO APM Demo - public end-user guide")
    canvas.drawRightString(letter[0] - doc.rightMargin, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_story(styles: dict[str, ParagraphStyle]) -> list:
    body = styles["GuideBody"]
    small = styles["GuideSmall"]
    code = styles["GuideCode"]

    story: list = [
        Paragraph("OCTO APM Demo - End-User Walkthrough", styles["GuideTitle"]),
        paragraph(
            "A public-safe LiveLab guide for running the buyer journey, payment simulation, support flow, "
            "admin simulations, OCI APM drilldowns, Log Analytics correlation, Availability Monitoring, "
            "Stack Monitoring discovery, and the simulated cyber-attack investigation.",
            styles["GuideSubtitle"],
        ),
        styled_table(
            [
                ["Item", "Value"],
                ["Shop URL", "${OCTO_LIVE_SHOP_URL} or https://shop.example.test"],
                ["Admin URL", "${OCTO_LIVE_ADMIN_URL} or https://admin.example.test"],
                ["Synthetic identity domain", "apex.example.test"],
                ["Admin sign-in", "Use the facilitator-provided local demo admin credentials from the deployment files."],
            ],
            [1.8 * inch, 4.8 * inch],
            body,
            small,
        ),
        Spacer(1, 0.12 * inch),
        paragraph(
            "Public copies must not include live domains, public IP addresses, OCIDs, tenancy names, wallet paths, "
            "passwords, or console account-header screenshots.",
            small,
        ),
        Paragraph("Before You Start", styles["GuideHeading"]),
        bullet_list(
            [
                "Use only fictional demo users and dummy payment values.",
                "Keep one OCI Console time window around the demo so traces, logs, metrics, RUM, and monitor runs line up.",
                "Copy order ids, trace ids, payment gateway request ids, ticket ids, and attack ids when the UI shows them.",
                "Do not paste secret values into screenshots, chat, tickets, commits, or public documentation.",
                "If a live endpoint is required, load it locally from private deployment files and keep it out of this PDF.",
            ],
            body,
        ),
        Paragraph("Prebuilt Demo Users", styles["GuideHeading"]),
        styled_table(
            [["Name", "User e-mail", "Persona"], *[list(user) for user in DEMO_USERS]],
            [1.35 * inch, 2.45 * inch, 2.75 * inch],
            body,
            small,
        ),
        Spacer(1, 0.1 * inch),
        paragraph(
            "For RUM demos, open the shop with one user at a time, for example: "
            "${OCTO_LIVE_SHOP_URL}/shop?synthetic_user=maya.ionescu@apex.example.test.",
            body,
        ),
        Paragraph("Lab 1 - Shop Order", styles["GuideHeading"]),
        numbered_list(
            [
                "Open the shop URL with synthetic_user=maya.ionescu@apex.example.test.",
                "Confirm the catalog renders from the database and the page shows observability indicators when configured.",
                "Open a drone product, add two drone products to the cart, and review the cart totals.",
                "Fill checkout with the fictional buyer Maya Ionescu, maya.ionescu@apex.example.test, Apex Field Services, phone +1 555 0184, and a synthetic operations address.",
                "Select Credit Card and use dummy VISA 4111111111111111 with future expiry, CVV 123, and postal code 10001.",
                "Click Place Order once. Copy the order id, trace id, and payment gateway request id if shown.",
            ],
            body,
        ),
        Paragraph("Expected signals", styles["GuideSubheading"]),
        bullet_list(
            [
                "RUM page view and custom actions for catalog load, add to cart, checkout start, and checkout completion.",
                "Shop spans for storefront, product lookup, cart, checkout validation, and order creation.",
                "Payment spans for simulated authorization, risk scoring, wallet/card metadata, and status.",
                "Java app-server spans for quote, payment verification, or support-side validation when the sidecar is enabled.",
                "SQL spans for customer, order, order item, payment transaction, and CRM sync writes.",
                "Structured app logs carrying oracleApmTraceId, oracleApmSpanId, order id, payment status, and gateway request id.",
            ],
            body,
        ),
        add_screenshot_marker("shop-checkout.png"),
        Paragraph("Lab 2 - Payment Variants", styles["GuideHeading"]),
        paragraph(
            "Repeat checkout with different users and payment methods to create useful APM, payment, SQL, and log diversity. "
            "The simulator records card brand, last four digits, expiry metadata, fingerprint, gateway status, risk score, "
            "and request id. It must not store or log full PAN or CVV.",
            body,
        ),
        styled_table(
            [
                ["Method", "User", "Dummy value", "Expected result"],
                ["Visa success", "maya.ionescu@apex.example.test", "4111111111111111", "Authorized credit-card path."],
                ["Mastercard success", "alex.chen@apex.example.test", "5555555555554444", "Authorized path with card_brand=mastercard."],
                ["Issuer decline", "nora.patel@apex.example.test", "4000000000000002", "Declined or review path with same trace context."],
                ["Apple Pay", "irina.marin@apex.example.test", "Simulated wallet token", "Tokenized wallet path with wallet_type=apple_pay."],
                ["Google Pay", "samuel.wright@apex.example.test", "Simulated wallet token", "Tokenized wallet path with wallet_type=google_pay."],
                ["Bank transfer", "daniel.rossi@apex.example.test", "Net 30", "Manual/offline path with method=bank_transfer."],
            ],
            [1.1 * inch, 1.85 * inch, 1.35 * inch, 2.25 * inch],
            body,
            small,
        ),
        Paragraph("Lab 3 - Support Ticket", styles["GuideHeading"]),
        numbered_list(
            [
                "Open the services page with the same fictional user.",
                "Book a service card if you want the support form pre-filled.",
                "Submit a ticket such as Need telemetry validation for order <order-id>.",
                "Confirm the ticket appears in the open-ticket list.",
            ],
            body,
        ),
        bullet_list(
            [
                "RUM page view for the services path.",
                "Service API spans for catalog and ticket creation.",
                "CRM integration spans when the support path is linked to the admin/CRM app.",
                "Logs with fictional user, request id, trace id, span id, ticket id, and order id.",
            ],
            body,
        ),
        PageBreak(),
        Paragraph("Lab 4 - Admin Simulations", styles["GuideHeading"]),
        numbered_list(
            [
                "Open the admin login page and sign in with the facilitator-provided local demo admin account.",
                "Open Settings or the Simulation area.",
                "Run Java Health to validate the Java app-server component instrumented with the OCI APM Java agent.",
                "Run Demo Storyboard to link shop, dummy payment, support, Java app-server, ATP SQL, and structured logs.",
                "Run Synthetic Users when visible, or ask the facilitator to confirm the VM timer is active.",
                "Run Generate Attack only when the room is ready to discuss the cyber investigation flow.",
                "Copy the returned trace id, attack id, order id, payment id, and ticket id when shown.",
            ],
            body,
        ),
        styled_table(
            [
                ["Control", "Backend route", "Observability purpose"],
                ["Java Health", "/api/shop/app-server/health", "Validates the Java APM agent path and app-server service."],
                ["Java scenario", "/api/shop/app-server/simulate/{scenario}", "Creates Java spans and app-server request evidence."],
                ["Payment scenario", "/api/shop/payment/simulate/{scenario}", "Creates payment gateway spans and logs."],
                ["Demo Storyboard", "/api/shop/demo/storyboard", "Creates an end-to-end buyer, payment, support, Java, SQL, and log path."],
                ["Attack Lab", "/api/shop/attack/simulate", "Creates MITRE, OSQuery, app log, trace, and metric evidence."],
                ["Synthetic Users", "/api/synthetic/users/run", "Creates fictional users and orders for RUM and APM Users."],
                ["360 Monitoring", "/api/observability/360", "Summarizes APM, logs, metrics, and availability evidence."],
            ],
            [1.2 * inch, 2.2 * inch, 3.05 * inch],
            body,
            small,
        ),
        add_screenshot_marker("admin-simulation.png"),
        PageBreak(),
        Paragraph("Lab 5 - OCI APM Walkthrough", styles["GuideHeading"]),
        paragraph(
            "Open OCI Console, select the demo compartment and APM domain, then use the same time window as the frontend order.",
            body,
        ),
        Preformatted(
            "OCI Console > Observability & Management > Application Performance Monitoring",
            code,
        ),
        Paragraph("APM Home and Service Monitoring", styles["GuideSubheading"]),
        styled_table(
            [
                ["Widget", "What to explain"],
                ["Services", "Active shop, admin/CRM, Java app-server, and database service names for the deployment."],
                ["Traces", "Recent traces, error traces, slow traces, and the handoff into Trace Explorer."],
                ["Web applications", "RUM web apps for the shop and admin frontend sessions."],
                ["Application servers", "Java app-server resource health, JVM metrics, server requests, and process metrics."],
                ["Monitors", "Availability percentage, failed runs, and selected global vantage points."],
                ["Alarms", "Monitoring/APM alarms that fired inside the scenario time window."],
            ],
            [1.4 * inch, 5.05 * inch],
            body,
            small,
        ),
        Paragraph("Trace Explorer", styles["GuideSubheading"]),
        numbered_list(
            [
                "Open Trace Explorer and set the time window around the checkout.",
                "Search by the copied trace id, or filter for workflow.id = 'checkout' or payment.gateway.request_id.",
                "Open the trace and walk the waterfall from browser/RUM to edge evidence, shop server, catalog/product lookup, checkout validation, payment, Java app-server, CRM sync, and ATP SQL spans.",
                "On the payment span, show method, status, risk score, gateway request id, card-safe metadata, and wallet metadata where present.",
                "On a SQL span, show db.system, db.operation, db.statement or preview, and DbOracleSqlId when present.",
                "Use oracleApmTraceId to pivot into OCI Logging or Log Analytics.",
            ],
            body,
        ),
        Paragraph("App Servers", styles["GuideSubheading"]),
        bullet_list(
            [
                "Select the Java app-server resource for the deployment.",
                "Check heap used, heap utilization, process CPU usage, garbage collection activity, threads, server requests, errors, and response time.",
                "Open service requests from the app-server details page and pivot back to the checkout or attack trace.",
                "If the page is empty, regenerate Java Health and confirm the Java sidecar is running with OCI APM Java agent app-server settings.",
            ],
            body,
        ),
        Paragraph("RUM", styles["GuideSubheading"]),
        bullet_list(
            [
                "Open Real User Monitoring and select the shop web application.",
                "Review Apdex, page response time, page views, AJAX calls, JavaScript errors, operating systems, browsers, and geography widgets.",
                "Open Users, search for maya.ionescu@apex.example.test, and drill into the session timeline.",
                "Switch to the admin web application to show the Demo Storyboard or Attack Lab session.",
            ],
            body,
        ),
        PageBreak(),
        Paragraph("Lab 6 - Availability, Logs, And Stack Monitoring", styles["GuideHeading"]),
        Paragraph("Availability Monitoring", styles["GuideSubheading"]),
        numbered_list(
            [
                "Open Availability Monitoring and show availability percentage for the shop and admin readiness monitors.",
                "Explain that selected global vantage points run the monitor and reveal regional failures or latency differences.",
                "Click a monitor, review target URL, interval, timeout, SSL validation, DNS override status, and selected vantage points.",
                "Open History, click a monitor run, and explain status, completion time, vantage point, waterfall/HAR, response headers, timings, screenshots, and trace details where available.",
                "To create a scripted browser monitor, use deploy/oci/ensure_availability_monitors.sh --scripted-browser to upload shop/tools/apm/octo-apm-demo-synthetic.spec.ts, validate it, then create or update a Scripted Browser monitor from selected global vantage points.",
            ],
            body,
        ),
        Paragraph("Log Analytics Drilldown", styles["GuideSubheading"]),
        numbered_list(
            [
                "Open Log Analytics Log Explorer for the order or attack time window.",
                "Filter by oracleApmTraceId = <trace-id>, security.attack.id = <attack-id>, or payment.gateway.request_id = <gateway-request-id>.",
                "Pin Trace ID, Span ID, Service, Host Name, User Name, Payment Method, Payment Status, Payment Gateway Request ID, MITRE Technique ID, OSQuery Finding, and msg.",
                "Open an app log row and use the trace id to return to APM Trace Explorer.",
                "For attack demos, open saved searches for attack timeline, detections, OSQuery findings, and edge detections.",
            ],
            body,
        ),
        Paragraph("Stack Monitoring Resource Discovery", styles["GuideSubheading"]),
        numbered_list(
            [
                "Open Stack Monitoring Resource Discovery after the Management Agent is active.",
                "Discover each app server as Resource Type Host.",
                "Use the Management Agent installed on that host.",
                "Select Stack Monitoring and Log Analytics so discovery sends resource context to both services.",
                "Open the discovered host resource and verify CPU, memory, filesystem, process, and availability metrics.",
            ],
            body,
        ),
        Paragraph("Lab 7 - Cyber-Attack Investigation Story", styles["GuideHeading"]),
        numbered_list(
            [
                "Start from the critical simulated alert generated by the Admin Attack Lab.",
                "Open the returned trace id in APM Trace Explorer and inspect the security.attack.kill_chain span group.",
                "Explain entry point, client IP placeholder, server connection, Java sidecar behavior, payment or checkout side effects, and ATP access.",
                "Pivot to Log Analytics with security.attack.id and oracleApmTraceId.",
                "Show MITRE mappings such as Initial Access T1190, Command and Scripting Interpreter T1059, Discovery T1046, and Exfiltration T1041 when present.",
                "Review OSQuery findings exported into OCI Logging and routed into Log Analytics.",
                "Use Cloud Guard service logs, Instance Security findings, host metrics, Java app-server metrics, and availability failures to complete the evidence story.",
            ],
            body,
        ),
        add_screenshot_marker("attack-investigation.png"),
        PageBreak(),
        Paragraph("Closeout Checklist", styles["GuideHeading"]),
        bullet_list(
            [
                "One successful order is visible in the shop/admin app and in APM Trace Explorer.",
                "Payment gateway spans and logs show safe payment attributes and gateway request id.",
                "SQL spans are visible for order, customer, payment transaction, and CRM sync operations.",
                "App logs correlate to the trace through oracleApmTraceId and oracleApmSpanId.",
                "The Java app-server appears in APM App Servers with heap, CPU, request, and error data.",
                "RUM shows the fictional user's browser session and action timeline.",
                "Availability Monitoring shows monitor status, vantage point evidence, HAR/waterfall, and screenshots where enabled.",
                "Log Analytics shows app, payment, security, OSQuery, and Cloud Guard evidence for the same scenario id.",
                "Stack Monitoring shows host CPU, memory, filesystem, process, and availability context.",
            ],
            body,
        ),
        Paragraph("Official OCI References", styles["GuideHeading"]),
        styled_table(
            [
                ["Topic", "Reference"],
                ["OCI Application Performance Monitoring", "docs.oracle.com/en-us/iaas/application-performance-monitoring/home.htm"],
                ["Trace Explorer", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-trace-explorer.html"],
                ["APM Browser Agent and RUM", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-browser-agent-real-user-monitoring.html"],
                ["Availability Monitoring scripts", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-script.html"],
                ["Availability Monitoring monitor history", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/view-monitor-history.html"],
                ["OCI Log Analytics", "docs.oracle.com/en-us/iaas/log-analytics/home.htm"],
                ["Ingest OCI service logs into Log Analytics", "docs.oracle.com/en-us/iaas/log-analytics/doc/ingest-logs-other-oci-services-using-service-connector.html"],
                ["Stack Monitoring resource discovery", "docs.oracle.com/en-us/iaas/stack-monitoring/doc/promotion-and-discovery.html"],
            ],
            [2.2 * inch, 4.25 * inch],
            body,
            small,
        ),
    ]
    return expand_screenshot_markers(story)


def add_screenshot_marker(filename: str) -> tuple[str, str]:
    return ("screenshot", filename)


def expand_screenshot_markers(story: list) -> list:
    expanded = []
    for item in story:
        if isinstance(item, tuple) and item[0] == "screenshot":
            add_screenshot(expanded, item[1])
        else:
            expanded.append(item)
    return expanded


def build_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    story = build_story(styles)
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=letter,
        rightMargin=0.52 * inch,
        leftMargin=0.52 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.56 * inch,
        title="OCTO APM Demo - End-User Walkthrough",
        author="OCTO APM Demo",
        subject="Public-safe end-user demo guide",
    )
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)


def main() -> None:
    build_pdf()
    print(f"wrote {PDF_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
