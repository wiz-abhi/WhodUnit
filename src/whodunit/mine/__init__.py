"""Whodunit mining stage: FP-growth over the trace x feature matrix, effect-size
gating, BH-FDR over the pre-enumerated family, calibrated abstention, and
topological demotion. Pure, deterministic, no network, no LLM."""

from __future__ import annotations

from whodunit.mine.api import default_min_support, mine
from whodunit.mine.config import MineConfig, MineResult

__all__ = ["MineConfig", "MineResult", "default_min_support", "mine"]
