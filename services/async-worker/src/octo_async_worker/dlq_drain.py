"""KG-035 — DLQ drain script.

Operator tool. Three modes:
  list   — XRANGE the DLQ, print each entry with run_id + error.
  retry  — re-XADD each entry back to the live stream with
           delivery_attempt reset to 1.
  drop   — XACK + XDEL each entry (permanent delete).

Usage:
  octo-dlq-drain --stream octo.orders.to-sync.dlq --mode list
  octo-dlq-drain --stream octo.orders.to-sync.dlq --mode retry --batch 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


async def run(*, stream: str, mode: str, batch: int, redis_url: str) -> int:
    import redis.asyncio as redis_async  # type: ignore

    r = redis_async.from_url(redis_url, decode_responses=False)
    try:
        entries = await r.xrange(stream, count=batch)
    except Exception as exc:
        logger.error("xrange failed: %s", exc)
        await r.aclose()
        return 2

    if not entries:
        print(f"DLQ {stream} empty")
        await r.aclose()
        return 0

    live_stream = stream
    if stream.endswith(".dlq"):
        live_stream = stream[:-4]

    for entry_id, fields in entries:
        entry_id_s = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
        run_id = (fields.get(b"run_id") or b"").decode()
        dlq_reason = (fields.get(b"dlq_reason") or b"").decode()
        payload = (fields.get(b"payload") or b"{}").decode()

        if mode == "list":
            print(json.dumps({
                "entry_id": entry_id_s,
                "run_id": run_id,
                "dlq_reason": dlq_reason,
                "payload": payload,
            }))

        elif mode == "retry":
            reset_fields = dict(fields)
            reset_fields[b"delivery_attempt"] = b"1"
            reset_fields.pop(b"dlq_reason", None)
            await r.xadd(live_stream, reset_fields, maxlen=10_000, approximate=True)
            await r.xdel(stream, entry_id_s)
            print(f"retried {entry_id_s} -> {live_stream}")

        elif mode == "drop":
            await r.xdel(stream, entry_id_s)
            print(f"dropped {entry_id_s}")

    await r.aclose()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stream", required=True, help="DLQ stream name, e.g. octo.orders.to-sync.dlq")
    ap.add_argument("--mode", choices=["list", "retry", "drop"], default="list")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--redis-url", default=os.getenv("OCTO_WORKER_REDIS_URL",
                    "redis://cache.octo-cache.svc.cluster.local:6379"))
    args = ap.parse_args()
    return asyncio.run(run(stream=args.stream, mode=args.mode, batch=args.batch, redis_url=args.redis_url))


if __name__ == "__main__":
    sys.exit(main())
