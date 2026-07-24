"""Pytest config local to the extractor tests.

Registers the ``live`` marker here (rather than editing the shared pyproject)
so ``@pytest.mark.live`` does not trigger an unknown-marker warning.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: end-to-end test against the live SigNoz stack (SIGNOZ_LIVE=1).",
    )
