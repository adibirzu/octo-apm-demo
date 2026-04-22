"""Tests for tools/create_la_source.py — the Log Analytics source/parser
registrar for app JSON logs.

The script is plan-only by default: it must print the request payload that
WOULD be sent to OCI and exit 0 without calling out. --apply is required
for the actual SDK call.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "create_la_source.py"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    if env is not None:
        e.update(env)
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=e,
        timeout=20,
    )


@pytest.mark.portability
def test_script_exists() -> None:
    assert SCRIPT.exists(), f"missing: {SCRIPT}"


@pytest.mark.portability
def test_dry_run_emits_payload_json() -> None:
    result = _run(
        "--la-namespace",
        "acme",
        "--la-log-group-id",
        "ocid1.loganalyticsloggroup.oc1..xxxx",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["name"] == "octo-shop-app-json"
    assert "parser" in payload
    # Core fields we expect the parser to extract
    for field in ("timestamp", "level", "trace_id", "oracleApmTraceId"):
        assert field in json.dumps(payload)


@pytest.mark.portability
def test_dry_run_does_not_require_oci_sdk() -> None:
    """Dry run must not import oci.log_analytics."""
    result = _run(
        "--la-namespace",
        "acme",
        "--la-log-group-id",
        "ocid1.loganalyticsloggroup.oc1..xxxx",
    )
    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 0


@pytest.mark.portability
def test_apply_without_credentials_fails_clearly() -> None:
    """With --apply set but no OCI config, fail with an informative error —
    never silently."""
    result = _run(
        "--apply",
        "--la-namespace",
        "acme",
        "--la-log-group-id",
        "ocid1.loganalyticsloggroup.oc1..xxxx",
        env={"OCI_CLI_AUTH": "instance_principal", "HOME": "/nonexistent"},
    )
    # Acceptable: non-zero with an OCI-related message, OR the oci package
    # is not even installed (also a clear signal).
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert any(
        needle in combined
        for needle in ("oci", "OCI", "InstancePrincipal", "ModuleNotFoundError")
    )
