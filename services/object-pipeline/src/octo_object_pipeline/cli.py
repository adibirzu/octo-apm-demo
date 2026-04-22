"""uvicorn entry point."""

from __future__ import annotations

import os

import uvicorn


def main() -> int:
    uvicorn.run(
        "octo_object_pipeline.api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
