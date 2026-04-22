"""KG-039 — remediator metrics tests."""

from __future__ import annotations

from octo_remediator.metrics import Metrics


def test_counter_increments() -> None:
    m = Metrics()
    m.inc_run(state="succeeded", tier="low")
    m.inc_run(state="succeeded", tier="low")
    m.inc_run(state="rejected", tier="high")

    out = m.render_prometheus()
    assert 'remediator_runs_total{state="succeeded",tier="low"} 2' in out
    assert 'remediator_runs_total{state="rejected",tier="high"} 1' in out


def test_histogram_buckets_include_observation() -> None:
    m = Metrics()
    m.observe_time_to_execute(0.3)  # <= 0.5 bucket
    m.observe_time_to_execute(2.0)  # <= 5.0 bucket
    m.observe_time_to_execute(45.0)  # <= 120 bucket

    out = m.render_prometheus()
    # Cumulative bucket counts
    assert 'remediator_run_time_to_execute_seconds_bucket{le="0.5"} 1' in out
    assert 'remediator_run_time_to_execute_seconds_bucket{le="5.0"} 2' in out
    assert 'remediator_run_time_to_execute_seconds_bucket{le="120.0"} 3' in out
    assert 'remediator_run_time_to_execute_seconds_count 3' in out
    assert 'remediator_run_time_to_execute_seconds_sum 47.3' in out


def test_render_is_prometheus_exposition_format() -> None:
    m = Metrics()
    m.inc_run(state="succeeded", tier="low")
    m.observe_time_to_propose(0.05)

    out = m.render_prometheus()
    assert "# HELP remediator_runs_total" in out
    assert "# TYPE remediator_runs_total counter" in out
    assert "# HELP remediator_run_time_to_propose_seconds" in out
    assert "# TYPE remediator_run_time_to_propose_seconds histogram" in out
