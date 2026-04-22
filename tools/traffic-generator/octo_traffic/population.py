"""Population — spawns sessions at ``target_rps`` with a concurrency cap,
keeps a running count of outcomes, and exports a summary on shutdown.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager

import httpx
import structlog
from opentelemetry import trace

from . import distributions as dist
from .config import TrafficConfig
from .session import Session, SessionOutcome
from .telemetry import init_tracing, shutdown as shutdown_telemetry

logger = structlog.get_logger(__name__)


class Population:
    def __init__(self, cfg: TrafficConfig):
        self.cfg = cfg
        self.outcomes: Counter[SessionOutcome] = Counter()
        self.sessions_launched: int = 0
        self._running: bool = False
        self._semaphore = asyncio.Semaphore(cfg.concurrent_session_limit)

    @asynccontextmanager
    async def _http_client(self):
        limits = httpx.Limits(
            max_connections=self.cfg.concurrent_session_limit * 2,
            max_keepalive_connections=self.cfg.concurrent_session_limit,
        )
        async with httpx.AsyncClient(
            base_url=self.cfg.shop_base_url,
            verify=self.cfg.verify_tls,
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=limits,
            follow_redirects=True,
            http2=True,
        ) as client:
            yield client

    async def run(self) -> None:
        dist.set_seed(self.cfg.seed)
        tracer = init_tracing(self.cfg)
        self._running = True
        stop_event = asyncio.Event()

        async def _stopper() -> None:
            if self.cfg.run_duration_seconds > 0:
                await asyncio.sleep(self.cfg.run_duration_seconds)
                stop_event.set()

        stop_task = asyncio.create_task(_stopper(), name="traffic-stopper")

        async with self._http_client() as client:
            active: set[asyncio.Task] = set()
            try:
                while not stop_event.is_set():
                    rps = self.cfg.target_rps * self.cfg.burst_multiplier
                    await asyncio.sleep(dist.poisson_arrival_inter_seconds(rps))
                    task = asyncio.create_task(
                        self._launch_one(client, tracer), name="traffic-session"
                    )
                    active.add(task)
                    task.add_done_callback(active.discard)
            finally:
                self._running = False
                if active:
                    await asyncio.gather(*active, return_exceptions=True)
                stop_task.cancel()
                shutdown_telemetry()
                self._log_summary()

    async def _launch_one(self, client: httpx.AsyncClient, tracer: trace.Tracer) -> None:
        async with self._semaphore:
            session = Session(self.cfg, client, tracer)
            self.sessions_launched += 1
            outcome = await session.run()
            self.outcomes[outcome] += 1

    def _log_summary(self) -> None:
        logger.info(
            "traffic.summary",
            sessions_launched=self.sessions_launched,
            outcomes={k.value: v for k, v in self.outcomes.items()},
        )
