"""Per-bucket handlers.

Adding a bucket: write a coroutine `async def process(object_data: bytes,
metadata: dict) -> ProcessingResult`, register it against a bucket name
in `HANDLERS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .events import emit


@dataclass
class ProcessingResult:
    ok: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[bytes, dict[str, Any]], Awaitable[ProcessingResult]]


_INVOICE_TOTAL_RE = re.compile(rb"total[:\s]+\$?(\d+[\.,]\d{2})", re.IGNORECASE)


async def process_invoice(body: bytes, metadata: dict[str, Any]) -> ProcessingResult:
    """Tiny invoice parser — look for 'Total: $XX.XX' in the PDF bytes.

    Production impl would use pdfplumber / Oracle Document Understanding;
    the regex here is illustrative and keeps the demo lean.
    """
    match = _INVOICE_TOTAL_RE.search(body)
    if not match:
        return ProcessingResult(ok=False, summary="no total found", data={"bytes": len(body)})

    total_str = match.group(1).decode("ascii", errors="replace").replace(",", ".")
    try:
        total = float(total_str)
    except ValueError:
        return ProcessingResult(ok=False, summary=f"invalid total: {total_str}")

    data = {
        "total": total,
        "currency": "USD",
        "object_name": metadata.get("object_name", ""),
    }

    await emit(
        event_type="com.octodemo.object-pipeline.invoice.processed",
        source="octo-object-pipeline",
        data=data,
    )

    return ProcessingResult(
        ok=True,
        summary=f"extracted total ${total:.2f}",
        data=data,
    )


async def process_catalog_image(body: bytes, metadata: dict[str, Any]) -> ProcessingResult:
    """Accept + size-check product images dropped into the catalog bucket."""
    size = len(body)
    if size > 5 * 1024 * 1024:  # 5 MB cap
        return ProcessingResult(ok=False, summary=f"image too large: {size} bytes")
    return ProcessingResult(ok=True, summary=f"accepted ({size} bytes)", data={"size": size})


HANDLERS: dict[str, Handler] = {
    "octo-invoices": process_invoice,
    "octo-catalog-images": process_catalog_image,
}


def get_handler(bucket: str) -> Handler | None:
    return HANDLERS.get(bucket)
