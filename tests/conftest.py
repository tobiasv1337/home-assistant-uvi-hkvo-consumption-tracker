"""Pytest setup helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        # Remove optional surrounding quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


_workspace_root = Path(__file__).resolve().parents[1]
_load_env_file(_workspace_root / ".env")


def pytest_addoption(parser: Any) -> None:
    """Add custom pytest command-line options."""
    parser.addoption(
        "--uvi-verbose",
        action="store_true",
        default=False,
        help="Enable verbose test output for UVI tests.",
    )


def pytest_collection_modifyitems(items: list[Any]) -> None:
    """Mark tests as offline by default unless explicitly marked online."""
    import pytest

    for item in items:
        if item.get_closest_marker("online") is None:
            item.add_marker(pytest.mark.offline)


def pytest_configure(config: Any) -> None:
    """Expose global verbosity flag for tests."""
    config.uvi_verbose = bool(config.getoption("--uvi-verbose"))
