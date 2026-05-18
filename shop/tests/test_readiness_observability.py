"""Readiness payload tests for observability configuration."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _dict_literal_keys(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    keys = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def test_shop_ready_reports_logging_configuration() -> None:
    source = (ROOT / "server/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    ready_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ready"
    ]

    assert ready_functions
    return_dicts = [
        node.value
        for node in ast.walk(ready_functions[0])
        if isinstance(node, ast.Return)
    ]
    ready_keys = set().union(*(_dict_literal_keys(node) for node in return_dicts))

    assert "apm_configured" in ready_keys
    assert "rum_configured" in ready_keys
    assert "logging_configured" in ready_keys
