"""CLI entry — runs the worker against WorkerConfig env vars."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from .config import WorkerConfig
from .telemetry import init_otel, script_span
from .worker import Worker


def main() -> int:
    cfg = WorkerConfig()
    logging.basicConfig(level=cfg.log_level.upper(), format="%(message)s")
    init_otel(
        service_name=cfg.service_name,
        resource_attributes={
            "messaging.system": "redis",
            "messaging.destination.name": ",".join(cfg.streams),
        },
    )

    worker = Worker(cfg)

    async def _run() -> int:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, worker.request_stop)
        with script_span(
            "async_worker.run",
            service_name=cfg.service_name,
            attributes={
                "messaging.system": "redis",
                "messaging.destination.name": ",".join(cfg.streams),
                "worker.run_once": cfg.run_once,
            },
        ):
            stats = await worker.run()
        print(stats.as_dict())
        return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
