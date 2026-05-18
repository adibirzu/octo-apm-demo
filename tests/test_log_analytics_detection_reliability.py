"""Log Analytics detection-rule and dashboard reliability tests."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_apply_helper():
    path = ROOT / "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py"
    spec = importlib.util.spec_from_file_location("octo_log_analytics_apply_helper_reliability", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rule_query(stem: str) -> str:
    return (ROOT / f"deploy/oci/log_analytics/searches/{stem}.sql").read_text(encoding="utf-8")


def _stats_metric_and_dimensions(query: str) -> tuple[str, list[str]]:
    match = re.search(
        r"\|\s*stats\s+count\s+as\s+([A-Za-z0-9_]+)\s+by\s+(.+)$",
        query,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, query
    dimensions = [
        field.strip().strip("'\"")
        for field in match.group(2).strip().split(",")
        if field.strip()
    ]
    return match.group(1), dimensions


def test_detection_rule_metadata_matches_scheduled_rule_queries() -> None:
    helper = _load_apply_helper()
    rule_files = {path.stem for path in (ROOT / "deploy/oci/log_analytics/searches").glob("rule-*.sql")}

    assert set(helper.DETECTION_RULES) == rule_files
    assert set(helper.DETECTION_RULE_DISPLAY_NAMES) == rule_files

    for stem, metadata in helper.DETECTION_RULES.items():
        metric_name, dimensions = _stats_metric_and_dimensions(_rule_query(stem))
        assert metric_name == metadata["metric"]
        assert dimensions == metadata["dimensions"]
        assert len(dimensions) <= 3
        assert helper.dimension_name(dimensions[0])


def test_log_analytics_apply_dry_run_is_offline(monkeypatch, capsys) -> None:
    helper = _load_apply_helper()

    def _fail(*_args, **_kwargs):
        raise AssertionError("dry-run must not call OCI lookup helpers")

    monkeypatch.setattr(helper, "existing_saved_search_id", _fail)
    monkeypatch.setattr(helper, "existing_scheduled_task_id", _fail)

    saved_search = helper.saved_search_payload(
        compartment_id="ocid1.compartment.oc1..example",
        display_name="Octo APM: Offline Dry Run",
        description="dry-run test",
        query="'Trace ID' != null | stats count as Events by 'Trace ID'",
    )
    saved_search_id = helper.upsert_saved_search("DEFAULT", saved_search, dry_run=True)
    assert saved_search_id.startswith("<dry-run-saved-search:")

    scheduled_rule = helper.scheduled_task_payload(
        compartment_id="ocid1.compartment.oc1..example",
        display_name="Octo APM Detection - Offline Dry Run",
        saved_search_id=saved_search_id,
        rule={
            "metric": "OfflineEvents",
            "dimensions": ["Trace ID"],
            "severity": "medium",
        },
    )
    helper.upsert_detection_rule("DEFAULT", "octo", scheduled_rule, dry_run=True)

    output = capsys.readouterr().out
    assert "DRY RUN: upsert saved search" in output
    assert "DRY RUN: upsert scheduled detection rule" in output


def test_dashboard_payload_compiles_every_widget_without_oci_calls() -> None:
    helper = _load_apply_helper()

    for dashboard_path in sorted((ROOT / "deploy/oci/log_analytics/dashboards").glob("*.json")):
        payload = helper.build_dashboard_payload("ocid1.compartment.oc1..example", dashboard_path)
        assert payload["displayName"]
        assert payload["tiles"]
        assert payload["savedSearches"]
        assert len(payload["tiles"]) == len(payload["savedSearches"])
        assert all(search["uiConfig"]["queryString"] for search in payload["savedSearches"])
        assert all(not helper.query_parameter_names(search["uiConfig"]["queryString"]) for search in payload["savedSearches"])


def test_clean_query_rejects_unsupported_colon_parameters(tmp_path: Path) -> None:
    helper = _load_apply_helper()
    query_path = tmp_path / "bad.sql"
    query_path.write_text("'Trace ID' = :trace_id | stats count as Events by 'Trace ID'", encoding="utf-8")

    try:
        helper.clean_query(query_path)
    except SystemExit as exc:
        assert ":trace_id" in str(exc)
    else:
        raise AssertionError("clean_query accepted an unsupported colon parameter")
