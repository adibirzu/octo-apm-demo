"""Redis-Streams async worker for octo-apm-demo.

Consumes events from Redis Streams with consumer-group semantics,
dispatches to per-stream handlers, retries with exponential backoff,
and routes persistent failures to a dead-letter stream.
"""

from .config import WorkerConfig
from .streams import Event, EventPublisher, StreamConsumer
from .worker import Worker

__all__ = ["WorkerConfig", "Event", "EventPublisher", "StreamConsumer", "Worker"]
__version__ = "1.0.0"
