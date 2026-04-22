"""Per-stream handler registry.

Adding a handler is two edits: write the coroutine in a new module,
then register it in HANDLERS below.
"""

from typing import Awaitable, Callable

from ..streams import Event
from .order_sync import handle as handle_order_sync

Handler = Callable[[Event], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "octo.orders.to-sync": handle_order_sync,
}


def get_handler(stream: str) -> Handler | None:
    return HANDLERS.get(stream)


__all__ = ["HANDLERS", "get_handler", "Handler"]
