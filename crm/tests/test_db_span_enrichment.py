from __future__ import annotations

from types import SimpleNamespace

from server.observability import db_spans


class _FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def is_recording(self) -> bool:
        return True

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


def test_compute_oracle_sql_id_is_stable_shape() -> None:
    sql_id = db_spans.compute_oracle_sql_id("select * from customers")

    assert sql_id == "gduf2uywbwbnv"
    assert len(sql_id) == 13


def test_db_span_enrichment_sets_apm_sql_attributes(monkeypatch) -> None:
    span = _FakeSpan()
    monkeypatch.setattr(db_spans.trace, "get_current_span", lambda: span)
    monkeypatch.setattr(
        db_spans,
        "cfg",
        SimpleNamespace(
            oracle_dsn="octoatp_low",
            oracle_user="ADMIN",
            atp_ocid="ocid1.autonomousdatabase.oc1..test",
        ),
    )

    db_spans._enrich_span_before_execute(
        conn=None,
        cursor=None,
        statement="select *\nfrom customers where id = :id",
        parameters={"id": 42},
        context=SimpleNamespace(),
        executemany=False,
    )

    assert span.attributes["DbStatement"] == "select * from customers where id = :id"
    assert span.attributes["DbOracleSqlId"]
    assert span.attributes["db.oracle.sql_id"] == span.attributes["DbOracleSqlId"]
    assert span.attributes["db.system"] == "oracle"
    assert span.attributes["component"] == "oracle"
    assert span.attributes["peer.service"] == "OracleATP:octoatp_low"
    assert span.attributes["db.oracle.atp_ocid"] == "ocid1.autonomousdatabase.oc1..test"
