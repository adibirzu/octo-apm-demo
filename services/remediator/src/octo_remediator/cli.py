"""Run the remediator FastAPI app under uvicorn."""

from __future__ import annotations

import os

import uvicorn


def main() -> int:
    uvicorn.run(
        "octo_remediator.api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "info"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
