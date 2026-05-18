"""Build the private live end-user APM troubleshooting PDF.

The generated PDFs are intentionally named with "private" so they are covered
by .gitignore. The script is placeholder-safe; pass live URLs through
environment variables when generating the private local artifact.
"""

from __future__ import annotations

import html
import os
import shutil
from datetime import datetime
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
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
LIVE_DIR = ROOT / "site" / "assets" / "demo" / "private-live"
OCI_DIR = ROOT / "site" / "assets" / "demo" / "private-oci-console"
SITE_PDF = ROOT / "site" / "assets" / "demo" / "octo-private-live-end-user-apm-guide.pdf"
OUTPUT_PDF = ROOT / "output" / "pdf" / "octo-private-live-end-user-apm-guide.pdf"


def live_shop_url() -> str:
    return os.getenv("OCTO_LIVE_SHOP_URL", "https://shop.example.test")


def live_admin_url() -> str:
    return os.getenv("OCTO_LIVE_ADMIN_URL", "https://admin.example.test")


def capture_time() -> str:
    value = os.getenv("OCTO_LIVE_CAPTURE_TIME")
    if value:
        return value
    return datetime.now().strftime("%Y-%m-%d %H:%M %Z").strip()


def make_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="GuideTitle",
            parent=styles["Title"],
            fontSize=22,
            leading=27,
            spaceAfter=8,
            textColor=colors.HexColor("#1f2a33"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideSubtitle",
            parent=styles["BodyText"],
            fontSize=10,
            leading=14,
            spaceAfter=10,
            textColor=colors.HexColor("#40515f"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideHeading",
            parent=styles["Heading2"],
            fontSize=14.5,
            leading=18,
            spaceBefore=10,
            spaceAfter=5,
            textColor=colors.HexColor("#1f2a33"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideSubheading",
            parent=styles["Heading3"],
            fontSize=11.2,
            leading=14,
            spaceBefore=7,
            spaceAfter=4,
            textColor=colors.HexColor("#2f3d46"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideBody",
            parent=styles["BodyText"],
            fontSize=8.8,
            leading=12,
            textColor=colors.HexColor("#27323a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="GuideSmall",
            parent=styles["BodyText"],
            fontSize=7.7,
            leading=10,
            textColor=colors.HexColor("#4e5d68"),
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
        leftIndent=15,
        bulletFontSize=7,
    )


def numbered_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(paragraph(item, style), bulletColor=colors.HexColor("#2f6f73")) for item in items],
        bulletType="1",
        leftIndent=15,
        bulletFontSize=7,
    )


def styled_table(rows: list[list[str]], widths: list[float], body: ParagraphStyle, small: ParagraphStyle) -> Table:
    data = [[cell(value, small if index == 0 else body) for value in row] for index, row in enumerate(rows)]
    table = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1f1")),
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


def image_path(directory: Path, filename: str) -> Path:
    path = directory / filename
    if not path.exists():
        raise SystemExit(f"Missing screenshot: {path.relative_to(ROOT)}")
    return path


def optional_image_path(directory: Path, filename: str) -> Path | None:
    path = directory / filename
    return path if path.exists() else None


def add_image(story: list, path: Path, width: float = 6.55 * inch, max_height: float = 6.8 * inch) -> None:
    image_width, image_height = ImageReader(str(path)).getSize()
    render_height = width * image_height / image_width
    if render_height > max_height:
        render_height = max_height
        width = render_height * image_width / image_height
    story.append(Image(str(path), width=width, height=render_height))
    story.append(Spacer(1, 0.08 * inch))


def add_step(story: list, styles: dict[str, ParagraphStyle], title: str, steps: list[str], screenshot: Path) -> None:
    story.append(Paragraph(title, styles["GuideHeading"]))
    story.append(numbered_list(steps, styles["GuideBody"]))
    add_image(story, screenshot, max_height=5.35 * inch)


def add_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#63707a"))
    canvas.drawString(doc.leftMargin, 0.34 * inch, "Private OCTO live demo guide - do not publish")
    canvas.drawRightString(letter[0] - doc.rightMargin, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_story(styles: dict[str, ParagraphStyle]) -> list:
    body = styles["GuideBody"]
    small = styles["GuideSmall"]
    shop = live_shop_url().rstrip("/")
    admin = live_admin_url().rstrip("/")

    story: list = [
        Paragraph("Private Live OCTO Demo Guide - End User and OCI APM Troubleshooting", styles["GuideTitle"]),
        paragraph(
            "This PDF is generated from a live Playwright run against the emdemo deployment. "
            "It includes real deployment domains and private screenshots, so it must stay in ignored local paths only.",
            styles["GuideSubtitle"],
        ),
        styled_table(
            [
                ["Field", "Value"],
                ["Shop", shop],
                ["Admin", admin],
                ["Captured", capture_time()],
                ["Generated outputs", f"{SITE_PDF.relative_to(ROOT)} and {OUTPUT_PDF.relative_to(ROOT)}"],
                ["Credential note", "Admin password is read from the ignored deployment credentials file and is not printed in this PDF."],
            ],
            [1.55 * inch, 5.05 * inch],
            body,
            small,
        ),
        Spacer(1, 0.12 * inch),
        paragraph(
            "Audience: demo end users and demo facilitators. Goal: run a buyer journey, generate observability data, "
            "then identify issues in OCI APM by pivoting through RUM, Trace Explorer, App Servers, Availability Monitoring, "
            "logs, and Log Analytics.",
            body,
        ),
        Paragraph("What Playwright Simulated", styles["GuideHeading"]),
        bullet_list(
            [
                "Opened the live shop with synthetic user maya.ionescu@apex.example.test.",
                "Loaded the catalog, added products to the cart, filled checkout, and placed a dummy-card order.",
                "Opened the support page and submitted a support ticket.",
                "Signed in to the live admin app with local deployment credentials.",
                "Ran Java Health, Demo Storyboard, Synthetic Users, Attack Lab, Availability plan, and 360 Monitoring.",
                "Captured screenshots after each major action into the ignored private-live asset folder.",
            ],
            body,
        ),
        Paragraph("Fast Demo Script", styles["GuideHeading"]),
        numbered_list(
            [
                f"Open {shop}/shop?synthetic_user=maya.ionescu@apex.example.test.",
                "Add two drones to the cart and fill the checkout form with fictional user data.",
                "Use dummy card 4111111111111111, future expiry, CVV 123, and a synthetic postal code.",
                "Place the order once. Copy the order id, trace id, and payment gateway request id if the page shows them.",
                f"Open {shop}/services?synthetic_user=maya.ionescu@apex.example.test and submit a support ticket.",
                f"Open {admin}/login, sign in with the local demo admin user, then go to Settings.",
                "Run Java Health and Demo Storyboard to force end-to-end spans through the shop, Java app-server, payment gateway simulation, admin/CRM, ATP SQL, and logs.",
                "Run Generate Attack to create the cyber investigation path for APM, logs, OSQuery findings, and MITRE attributes.",
            ],
            body,
        ),
        PageBreak(),
    ]

    add_step(
        story,
        styles,
        "Step 1 - Open Drone Shop Catalog",
        [
            f"Navigate to {shop}/shop with the synthetic_user query parameter.",
            "Confirm the RUM/APM indicators and product cards render.",
            "Use this page load as the RUM session start for the APM troubleshooting section.",
        ],
        image_path(LIVE_DIR, "shop-catalog-live.png"),
    )
    add_step(
        story,
        styles,
        "Step 2 - Add Drones and Prepare Checkout",
        [
            "Click Add to Cart on two products.",
            "Fill the buyer fields with fictional corporate user data.",
            "Select Credit Card and enter only dummy payment values.",
        ],
        image_path(LIVE_DIR, "shop-checkout-ready-live.png"),
    )
    add_step(
        story,
        styles,
        "Step 3 - Place Order",
        [
            "Click Place Order once.",
            "Capture the returned order id, trace id, and gateway request id if displayed.",
            "Use the trace id first in APM Trace Explorer; use the order id and gateway request id in Log Analytics.",
        ],
        image_path(LIVE_DIR, "shop-order-complete-live.png"),
    )
    story.append(PageBreak())
    add_step(
        story,
        styles,
        "Step 4 - Create Support Signal",
        [
            f"Open {shop}/services with the same synthetic user.",
            "Book or submit a support ticket related to the order.",
            "Use this to show a second frontend route and a second backend workflow in the same demo window.",
        ],
        image_path(LIVE_DIR, "shop-support-ticket-ready-live.png"),
    )
    add_step(
        story,
        styles,
        "Step 5 - Confirm Support Ticket",
        [
            "Submit the ticket.",
            "Confirm the ticket appears in the list.",
            "In APM, expect service/ticket spans and logs correlated by trace id and request id.",
        ],
        image_path(LIVE_DIR, "shop-support-ticket-submitted-live.png"),
    )
    story.append(PageBreak())
    add_step(
        story,
        styles,
        "Step 6 - Open Admin Simulation Lab",
        [
            f"Open {admin}/login and sign in with the ignored deployment credentials.",
            "Go to the Settings or Simulation page.",
            "Confirm Java APM, Demo Storyboard, Synthetic Users, Attack Lab, Availability, and 360 Monitoring controls are visible.",
        ],
        image_path(LIVE_DIR, "admin-simulation-live.png"),
    )
    add_step(
        story,
        styles,
        "Step 7 - Validate Java APM Health",
        [
            "Click Java Health.",
            "Confirm the response shows the Java app-server path is healthy.",
            "Use this before opening APM App Servers; without Java traffic, the App Servers page can look empty.",
        ],
        image_path(LIVE_DIR, "admin-java-apm-health-live.png"),
    )
    story.append(PageBreak())
    add_step(
        story,
        styles,
        "Step 8 - Run Demo Storyboard",
        [
            "Click Run Story.",
            "Wait for the linked buyer, payment, Java, support, SQL, and log path to finish.",
            "Copy any returned trace id, order id, payment id, and ticket id.",
        ],
        image_path(LIVE_DIR, "admin-storyboard-output-live.png"),
    )
    add_step(
        story,
        styles,
        "Step 9 - Generate Synthetic Users",
        [
            "Click Generate Users.",
            "Use the generated identities to populate RUM, APM Users, orders, payments, and logs.",
            "In APM RUM, filter later by apex.example.test users.",
        ],
        image_path(LIVE_DIR, "admin-synthetic-users-output-live.png"),
    )
    story.append(PageBreak())
    add_step(
        story,
        styles,
        "Step 10 - Generate Attack Path",
        [
            "Click Generate Attack.",
            "Copy the returned attack id and trace id.",
            "Use the attack id in Log Analytics and the trace id in APM Trace Explorer.",
        ],
        image_path(LIVE_DIR, "admin-attack-lab-output-live.png"),
    )
    add_step(
        story,
        styles,
        "Step 11 - Review Availability Plan",
        [
            "Click Show Global Monitor Plan.",
            "Use the plan to explain the shop and admin monitor targets, intervals, and vantage points.",
            "In OCI APM Availability Monitoring, compare monitor failures to app logs and traces.",
        ],
        image_path(LIVE_DIR, "admin-availability-plan-live.png"),
    )
    story.append(PageBreak())
    add_step(
        story,
        styles,
        "Step 12 - Review 360 Monitoring",
        [
            "Open the Admin 360 Monitoring page.",
            "Use this page as the bridge from the application to OCI APM, Logging, Log Analytics, metrics, and security signals.",
            "If data is missing, regenerate Java Health, Demo Storyboard, and Attack Lab before troubleshooting in OCI.",
        ],
        image_path(LIVE_DIR, "admin-360-monitoring-live.png"),
    )

    story.append(PageBreak())
    story.append(Paragraph("OCI APM Troubleshooting Workflow", styles["GuideHeading"]))
    story.append(
        paragraph(
            "Use the same time window as the Playwright run. Start with the order trace, then move from exact request evidence "
            "to aggregate service, user, app-server, synthetic monitor, and log evidence.",
            body,
        )
    )
    story.append(
        styled_table(
            [
                ["Symptom", "Where to look first", "What identifies the issue"],
                ["Checkout is slow", "Trace Explorer", "Longest spans, SQL duration, Java payment verification, or CRM sync span."],
                ["Order failed", "Trace Explorer and Log Analytics", "Root span status, payment.status, exception span, and matching app log."],
                ["App Servers page is empty", "Java Health and APM App Servers", "No Java request after agent startup, missing agent flags, or wrong APM domain."],
                ["RUM has no user session", "Real User Monitoring", "Browser agent missing, blocked script, wrong web app, or username not set."],
                ["Logs do not correlate", "Log Analytics", "Missing oracleApmTraceId or oracleApmSpanId fields in app log records."],
                ["Monitor failed globally", "Availability Monitoring", "Failed vantage point, HAR waterfall, screenshot, DNS, TLS, or HTTP status evidence."],
            ],
            [1.35 * inch, 1.55 * inch, 3.65 * inch],
            body,
            small,
        )
    )
    story.append(Paragraph("1. Find The Order Trace", styles["GuideSubheading"]))
    story.append(
        numbered_list(
            [
                "Open OCI Console > Observability & Management > Application Performance Monitoring > Trace Explorer.",
                "Select the emdemo compartment and the correct APM domain.",
                "Set the time window to the Playwright run.",
                "Search by copied trace id. If no trace id is available, filter by workflow.id = 'checkout', payment.gateway.request_id, or operation names containing checkout.",
                "Open the trace details and inspect the waterfall from RUM/browser to shop, payment gateway simulation, Java app-server, admin/CRM, and ATP SQL.",
                "Sort spans by duration and errors. The first high-duration or error span usually gives the fastest root-cause lead.",
            ],
            body,
        )
    )
    apm_trace = optional_image_path(OCI_DIR, "oci-apm-trace-explorer-live.png")
    if apm_trace:
        add_image(story, apm_trace, max_height=3.8 * inch)

    story.append(Paragraph("2. Confirm Browser/User Evidence In RUM", styles["GuideSubheading"]))
    story.append(
        numbered_list(
            [
                "Open Real User Monitoring for the shop web application.",
                "Search for maya.ionescu@apex.example.test or another synthetic user used in the run.",
                "Open the session and confirm page load, add-to-cart, checkout start, checkout complete or checkout error, and support page activity.",
                "If backend traces exist but RUM is empty, check the browser agent snippet, CSP, blocked JavaScript, and whether the app sets the username before the RUM agent loads.",
            ],
            body,
        )
    )
    rum = optional_image_path(OCI_DIR, "oci-apm-rum-live.png")
    if rum:
        add_image(story, rum, max_height=3.4 * inch)

    story.append(Paragraph("3. Check App Servers For The Java Sidecar", styles["GuideSubheading"]))
    story.append(
        numbered_list(
            [
                "Open APM App Servers and choose the Java app-server resource.",
                "Set the same time range and confirm heap used, heap utilization, process CPU, garbage collection, request count, errors, and response time.",
                "Drill into server requests and pivot back to the trace containing Java Health, payment verification, storyboard, or attack spans.",
                "If empty, rerun Java Health from Admin, then check agent startup logs, service name, private data key, upload endpoint, and selected APM domain.",
            ],
            body,
        )
    )

    story.append(Paragraph("4. Pivot To Logs And Log Analytics", styles["GuideSubheading"]))
    story.append(
        numbered_list(
            [
                "Open OCI Logging or Log Analytics for the same time window.",
                "Filter by oracleApmTraceId, oracleApmSpanId, order id, payment gateway request id, or security.attack.id.",
                "Pin service, host, user, route, status, payment.status, mitre.technique_id, osquery finding, and original log content.",
                "If traces exist but logs do not, check Logging agent config, Service Connector Hub, parser/source mapping, and whether the app emits trace ids into structured logs.",
            ],
            body,
        )
    )
    logan = optional_image_path(OCI_DIR, "oci-log-analytics-explorer-live.png")
    if logan:
        add_image(story, logan, max_height=3.2 * inch)

    story.append(Paragraph("5. Use Availability Monitoring For Outside-In Evidence", styles["GuideSubheading"]))
    story.append(
        numbered_list(
            [
                "Open Availability Monitoring and choose the shop or admin monitor.",
                "Review availability percentage and failed global vantage points.",
                "Open a failed or slow monitor run and inspect HAR waterfall, screenshots, timings, DNS, TLS, and response status.",
                "Compare the monitor time to LB/WAF/app logs and APM traces.",
            ],
            body,
        )
    )
    availability = optional_image_path(OCI_DIR, "oci-availability-monitoring-live.png")
    if availability:
        add_image(story, availability, max_height=3.2 * inch)

    story.append(PageBreak())
    story.append(Paragraph("Closing Talk Track", styles["GuideHeading"]))
    story.append(
        bullet_list(
            [
                "Start with the user action: the shopper opened the shop, added drones, paid with dummy data, and opened support.",
                "Prove browser impact in RUM and exact backend path in Trace Explorer.",
                "Use App Servers to prove the Java component has JVM and request visibility.",
                "Use SQL spans to prove ATP work and Log Analytics to prove durable app/payment/security evidence.",
                "Use Availability Monitoring to prove whether outside vantage points saw the same symptom.",
                "For attack demos, pivot by security.attack.id and mitre.technique_id, then validate OSQuery and Cloud Guard evidence.",
            ],
            body,
        )
    )
    story.append(Paragraph("Official References Used By This Guide", styles["GuideHeading"]))
    story.append(
        styled_table(
            [
                ["Topic", "Reference"],
                ["APM overview", "docs.oracle.com/en-us/iaas/application-performance-monitoring/"],
                ["Trace Explorer", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-trace-explorer.html"],
                ["Monitor traces", "docs.oracle.com/iaas/application-performance-monitoring/doc/monitor-traces-trace-explorer.html"],
                ["APM metrics and app-server metrics", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html"],
                ["Availability Monitoring", "docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/monitor-application-performance-using-synthetic-monitoring.html"],
            ],
            [1.85 * inch, 4.75 * inch],
            body,
            small,
        )
    )
    story.append(
        paragraph(
            "Private handling: this PDF contains real deployment domains and private screenshots. Keep it in ignored local paths only.",
            small,
        )
    )
    return story


def build_pdf() -> None:
    SITE_PDF.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    story = build_story(styles)
    doc = SimpleDocTemplate(
        str(SITE_PDF),
        pagesize=letter,
        rightMargin=0.52 * inch,
        leftMargin=0.52 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.56 * inch,
        title="Private Live OCTO Demo Guide",
        author="OCTO APM Demo",
        subject="Private live end-user and OCI APM troubleshooting guide",
    )
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    shutil.copyfile(SITE_PDF, OUTPUT_PDF)


def main() -> None:
    build_pdf()
    print(f"wrote {SITE_PDF.relative_to(ROOT)}")
    print(f"wrote {OUTPUT_PDF.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
