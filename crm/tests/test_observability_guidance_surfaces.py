from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
REPO_ROOT = ROOT.parent


def test_simulation_page_contains_presenter_event_generation_guide() -> None:
    template = (ROOT / "server/templates/simulation.html").read_text()

    assert "Event Generation Guide" in template
    assert "TraceId" in template
    assert "Trace ID" in template
    assert "Open Captured Data Center" in template
    assert "OCTO APM - checkout end-to-end" in template
    assert "OCTO APM - payment Java sidecar" in template
    assert "checkout-payment-correlation" in template
    assert "attack-lab-trace-timeline" in template
    assert "payment-gateway-security-triage" in template
    assert "renderEvidencePivots" in template


def test_captured_data_page_builds_safe_apm_and_log_analytics_pivots() -> None:
    template = (ROOT / "server/templates/captured_data.html").read_text()

    assert "Captured Data Center" in template
    assert "Operator evidence center" in template
    assert "Trace ID" in template
    assert "Payment Gateway Request ID" in template
    assert "Attack ID" in template
    assert "Assistant Session ID" in template
    assert "OCTO APM - trace drilldown" in template
    assert "checkout-payment-correlation" in template
    assert "genai-assistant-llmetry" in template
    assert "DbOracleSqlId" in template
    assert "does not expose secrets" in template

    blocked_terms = ["oci_apm_private", "wallet_", "password", "ocid1."]
    lowered = template.lower()
    for term in blocked_terms:
        assert term not in lowered


def test_captured_data_route_and_navigation_are_registered() -> None:
    main = (ROOT / "server/main.py").read_text()
    base = (ROOT / "server/templates/base.html").read_text()

    assert '@app.get("/captured-data"' in main
    assert '"captured_data"' in main
    assert "Captured Data" in base
    assert "nav_captured_data" in base


def test_event_generation_guide_is_in_mkdocs_nav_and_references_real_assets() -> None:
    guide = (REPO_ROOT / "site/observability-v2/event-generation-guide.md").read_text()
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text()

    assert "Event generation guide: observability-v2/event-generation-guide.md" in mkdocs
    for saved_search in (
        "checkout-payment-correlation",
        "payment-gateway-security-triage",
        "attack-lab-trace-timeline",
        "genai-assistant-llmetry",
        "service-trace-log-coverage",
    ):
        assert saved_search in guide
        assert (REPO_ROOT / f"deploy/oci/log_analytics/searches/{saved_search}.sql").exists()

    for saved_query in (
        "checkout-end-to-end.json",
        "payment-java-sidecar.json",
        "assistant-genai-llmetry.json",
        "service-errors.json",
    ):
        assert (REPO_ROOT / f"deploy/oci/apm/saved-queries/{saved_query}").exists()


def test_public_docs_describe_vm_and_oke_without_live_tenancy_details() -> None:
    platform = (REPO_ROOT / "site/architecture/platform-overview.md").read_text()
    system_design = (REPO_ROOT / "site/architecture/system-design.md").read_text()
    observability = (REPO_ROOT / "site/observability-v2/index.md").read_text()
    deployment_options = (REPO_ROOT / "site/getting-started/deployment-options.md").read_text()

    combined = "\n".join([platform, system_design, observability, deployment_options])
    assert "Private VM/Compute" in combined
    assert "OKE runtime" in combined
    assert "Captured Data Center" in combined
    assert "Guided event generation" in combined
    assert "/captured-data" in combined

    public_docs = "\n".join(
        path.read_text(errors="ignore")
        for base in (REPO_ROOT / "site",)
        for path in base.rglob("*.md")
        if "/private-" not in path.as_posix()
    )
    forbidden_patterns = [
        "octodemo.cloud",
        "emdemo",
        "161.153.",
        "132.226.",
        "10.42.",
        "82.77.",
        "${OCIR_TENANCY}",
        "attack-851e80f8751b",
    ]
    lowered = public_docs.lower()
    for token in forbidden_patterns:
        assert token.lower() not in lowered
