"""Ensure pytest-asyncio is active even when the tests dir is
invoked outside the client/pyproject.toml rootdir."""

import pytest

pytest_plugins = ("pytest_asyncio",)
