from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISHED_ARCHITECTURE_FILES = [
    REPO_ROOT / "site/architecture/diagrams/private-demo-observability-reference.drawio",
    REPO_ROOT / "site/architecture/diagrams/private-demo-observability-reference.svg",
]
IPV4_LITERAL = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def test_published_architecture_diagram_has_no_ip_literals() -> None:
    for path in PUBLISHED_ARCHITECTURE_FILES:
        content = path.read_text(encoding="utf-8")

        assert not IPV4_LITERAL.search(content), path
        assert "LB IP" not in content
        assert "operator IP" not in content


def test_private_ip_diagram_variants_are_ignored() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "site/architecture/diagrams/*with-ips*" in gitignore
    assert "site/architecture/diagrams/*resolved*" in gitignore
    assert "site/architecture/diagrams/*.local.drawio" in gitignore
    assert "site/architecture/diagrams/*.local.svg" in gitignore
