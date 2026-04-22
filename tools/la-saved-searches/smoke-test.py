"""Trace ↔ Log round-trip smoke test.

1. Emit a trace with a known trace_id from a small Python script.
2. Poll OCI Log Analytics for ``octo-shop-app-json`` records matching
   that trace_id.
3. Assert at least one record arrives within the ingestion SLA
   (default 180 s — configurable via LA_INGESTION_TIMEOUT_SECONDS).

Run **after** the shop has processed at least one request with the
emitted trace context. In practice: run the traffic generator for a
minute, then run this with its most recent trace id.

Usage:
    python tools/la-saved-searches/smoke-test.py \\
        --la-namespace <namespace> \\
        --trace-id <hex-32> \\
        [--timeout 300]

Exit codes:
    0 — round-trip succeeded (log record found)
    1 — timed out waiting for the log record
    2 — invalid arguments / OCI auth failure
"""

from __future__ import annotations

import argparse
import re
import sys
import time


TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--la-namespace", required=True)
    p.add_argument("--trace-id", required=True, help="32-hex-character OTel trace id")
    p.add_argument("--timeout", type=int, default=180, help="Seconds to wait for LA ingestion")
    p.add_argument("--poll-interval", type=int, default=10)
    return p.parse_args()


def main() -> int:
    args = _parse()

    if not TRACE_ID_RE.match(args.trace_id):
        print(f"invalid trace_id (expected 32 lowercase hex chars, got '{args.trace_id}')", file=sys.stderr)
        return 2

    try:
        import oci  # type: ignore
    except ImportError:
        print("oci python SDK not installed (pip install oci)", file=sys.stderr)
        return 2

    try:
        config = oci.config.from_file()
        client = oci.log_analytics.LogAnalyticsClient(config)
    except Exception as exc:
        print(f"OCI auth failed: {exc}", file=sys.stderr)
        return 2

    query = (
        f"'Log Source' = 'octo-shop-app-json' "
        f"and oracleApmTraceId = '{args.trace_id}' | head limit = 1"
    )

    deadline = time.time() + args.timeout
    poll = 0
    while time.time() < deadline:
        poll += 1
        try:
            resp = client.query(
                namespace_name=args.la_namespace,
                query_details=oci.log_analytics.models.QueryDetails(
                    query_string=query,
                    scope_filters=[],
                    compartment_id=None,  # whole tenancy scope
                    sub_system="LOG",
                ),
            )
            results = (resp.data.items or []) if hasattr(resp.data, "items") else []
            if results:
                print(
                    f"[poll {poll}] trace_id={args.trace_id} found in LA "
                    f"after {int(time.time() - (deadline - args.timeout))}s"
                )
                return 0
        except Exception as exc:  # pragma: no cover — OCI SDK surface
            print(f"[poll {poll}] LA query failed: {exc}", file=sys.stderr)
        time.sleep(args.poll_interval)

    print(
        f"TIMEOUT — no LA record for trace_id={args.trace_id} after "
        f"{args.timeout}s. Check that the app is emitting "
        f"oracleApmTraceId on logs and that the Service Connector to LA "
        f"is running (deploy/terraform module la_pipeline_app_logs).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
