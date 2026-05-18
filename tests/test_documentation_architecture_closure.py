from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _drawio_layers(path: Path) -> tuple[list[str], set[str]]:
    root = ET.parse(path).getroot()
    cells = root.findall(".//mxCell")
    layers = [
        cell.get("value") or ""
        for cell in cells
        if cell.get("parent") == "0" and cell.get("id") != "0"
    ]
    layer_ids = {
        cell.get("id")
        for cell in cells
        if cell.get("parent") == "0" and cell.get("id") != "0"
    }
    used_layers = {
        cell.get("parent")
        for cell in cells
        if cell.get("id") not in {"0"} and cell.get("parent") in layer_ids
    }
    return layers, used_layers


def test_drawio_sources_are_layered_and_editable() -> None:
    diagram_dir = REPO_ROOT / "site/architecture/diagrams"
    expected = {
        "platform-overview.drawio": [
            "Users and edge controls",
            "Application runtime",
            "Data plane",
            "Observability services",
        ],
        "observability-flow.drawio": [
            "App instrumentation and correlation",
            "OCI observability destinations",
            "MELTS legend",
        ],
        "deploy-topology.drawio": [
            "Build and validation path",
            "OKE target",
            "VM and Compute targets",
            "Local regression target",
        ],
        "private-demo-observability-reference.drawio": [
            "External entry and edge",
            "Private app compute",
            "Data and AI services",
            "Observability and security plane",
        ],
    }

    for filename, required_layer_fragments in expected.items():
        layers, used_layers = _drawio_layers(diagram_dir / filename)
        assert len(layers) >= 4
        assert len(used_layers) >= 4
        joined = "\n".join(layers)
        for fragment in required_layer_fragments:
            assert fragment in joined


def test_architecture_docs_keep_admin_ai_off_customer_surface() -> None:
    system_design = (REPO_ROOT / "site/architecture/system-design.md").read_text()
    platform = (REPO_ROOT / "site/architecture/platform-overview.md").read_text()
    coordinator = (REPO_ROOT / "site/integrations/coordinator.md").read_text()

    combined = "\n".join([system_design, platform, coordinator])
    assert "Coordinator admin-only" in combined
    assert "admin Query Lab + Select AI" in combined
    assert "Workflow Gateway admin labs" in combined
    assert "coordinator.scope.enforced" in combined
    assert "coordinator.auth.mode" in combined
    assert "raw_prompt_logged=false" in combined
    assert 'Coordinator -->|"MCP tools"| DroneShop' not in combined


def test_docs_include_release_and_troubleshooting_closure() -> None:
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text()
    deploy_readiness = (REPO_ROOT / "site/operations/deploy-readiness.md").read_text()
    dashboards = (REPO_ROOT / "site/observability-v2/log-analytics-dashboards.md").read_text()
    diagrams = (REPO_ROOT / "site/architecture/diagrams/README.md").read_text()

    assert "Synthetic monitoring: observability-v2/synthetic-monitoring.md" in mkdocs
    assert "VERIFY PASSED" in deploy_readiness
    assert "0 warning" in deploy_readiness
    assert "connector-live-log-coverage.sql" in dashboards
    assert "oke-onm-ingestion-health.sql" in dashboards
    assert "Layer authoring" in diagrams
    assert "flow movement" in diagrams.lower()
