"""CLI entry point — used by octo-load-control's EDGE_FUZZ executor
and as a standalone ops tool.

  octo-edge-fuzz --target https://api.drone.octodemo.cloud \\
                 --count 500 --run-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .fuzzer import EdgeFuzzer


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, help="Base URL of the target edge.")
    ap.add_argument("--endpoint", default="/api/admin/chaos/apply")
    ap.add_argument("--count", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--operator", default="edge-fuzzer")
    args = ap.parse_args()

    fuzzer = EdgeFuzzer(
        target_url=args.target,
        target_endpoint=args.endpoint,
        requests_count=args.count,
        concurrency=args.concurrency,
        run_id=args.run_id,
        operator=args.operator,
    )
    stats = asyncio.run(fuzzer.run())
    print(stats.as_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
