"""Pytest configuration local to the compiler test suite."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: differential-verification tests that require a running SigNoz stack "
        "(gated on SIGNOZ_LIVE=1).",
    )
