"""Register an OCI Log Analytics source + parser for OCTO Drone Shop
JSON logs so Service Connector-ingested logs land with structured fields
(trace_id, oracleApmTraceId, level, message, request_id).

The app uses a consistent JSON log schema via server/observability/*; this
script creates the matching LA source so searches like
  'Log Source' = 'octo-shop-app-json' | where oracleApmTraceId = '<x>'
work immediately.

Dry run (default): prints the payload that WOULD be sent, exits 0.
Apply mode: posts to OCI Log Analytics via the python SDK.

Usage:
  python3 tools/create_la_source.py \\
      --la-namespace <ns> \\
      --la-log-group-id <ocid> \\
      [--name octo-shop-app-json] \\
      [--apply]
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import asdict, dataclass, field


def _imds_reachable(*, timeout: float = 1.5) -> bool:
    """Return True if the OCI instance metadata endpoint accepts a TCP
    connection within ``timeout`` seconds. Avoids long hangs when run off
    an OCI instance."""
    try:
        with socket.create_connection(("169.254.169.254", 80), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class LAField:
    name: str
    data_type: str = "STRING"


@dataclass(frozen=True)
class LAParser:
    name: str
    content: str
    type: str = "JSON"
    fields: tuple[LAField, ...] = field(default=tuple)


@dataclass(frozen=True)
class LASource:
    name: str
    description: str
    la_log_group_id: str
    parser: LAParser


def build_payload(
    *,
    name: str,
    la_log_group_id: str,
) -> dict:
    parser = LAParser(
        name=f"{name}-parser",
        content=(
            # JSON parser definition — the fields list enumerates the keys we
            # want LA to promote to searchable columns.
            '{"fields": ['
            '"timestamp","level","message","trace_id","span_id",'
            '"oracleApmTraceId","request_id","user_id","route","http_status"'
            "]}"
        ),
        fields=(
            LAField("timestamp", "TIMESTAMP"),
            LAField("level"),
            LAField("message"),
            LAField("trace_id"),
            LAField("span_id"),
            LAField("oracleApmTraceId"),
            LAField("request_id"),
            LAField("user_id"),
            LAField("route"),
            LAField("http_status", "INTEGER"),
        ),
    )
    source = LASource(
        name=name,
        description=(
            "OCTO Drone Shop JSON app logs; preserves APM trace context "
            "(oracleApmTraceId) for cross-signal correlation."
        ),
        la_log_group_id=la_log_group_id,
        parser=parser,
    )
    # dataclasses.asdict handles the nested tuple-of-dataclasses correctly.
    return asdict(source)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--la-namespace", required=True, help="OCI Log Analytics namespace")
    ap.add_argument("--la-log-group-id", required=True, help="OCI LA log group OCID")
    ap.add_argument("--name", default="octo-shop-app-json", help="LA source name")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually call OCI (requires `oci` package + valid auth). Without this flag, prints payload and exits.",
    )
    args = ap.parse_args(argv)

    payload = build_payload(name=args.name, la_log_group_id=args.la_log_group_id)
    print(json.dumps(payload, indent=2))

    if not args.apply:
        return 0

    # Import lazily so `--apply`-less dry runs have zero dependency on oci.
    try:
        import oci  # type: ignore
    except ImportError as exc:  # pragma: no cover — environment dependent
        print(f"oci package not installed: {exc}", file=sys.stderr)
        return 2

    try:
        config = oci.config.from_file()
        signer = None
    except Exception:  # pragma: no cover
        # Fall back to InstancePrincipal only if the IMDS endpoint is
        # actually reachable. Probing first avoids a 20+ second hang when
        # running outside an OCI instance.
        if not _imds_reachable(timeout=1.5):
            print(
                "OCI config file not found and IMDS (169.254.169.254) is unreachable; "
                "cannot resolve credentials. Set up ~/.oci/config or run on an OCI instance.",
                file=sys.stderr,
            )
            return 3
        try:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            config = {}
        except Exception as exc:
            print(
                f"Could not initialize OCI InstancePrincipal auth: {exc}",
                file=sys.stderr,
            )
            return 3

    client = oci.log_analytics.LogAnalyticsClient(config, signer=signer)  # type: ignore[arg-type]
    # NOTE: the exact create-source API shape evolves with the SDK; keep
    # this call behind --apply so dry-run tests never touch it. Real
    # rollout uses the current SDK reference.
    try:
        client.upsert_source(
            namespace_name=args.la_namespace,
            upsert_log_analytics_source_details=payload,  # type: ignore[arg-type]
        )
    except AttributeError:
        # Older SDKs used create_source
        client.create_log_analytics_source(  # type: ignore[attr-defined]
            namespace_name=args.la_namespace,
            create_log_analytics_source_details=payload,
        )

    print("Source registered.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
