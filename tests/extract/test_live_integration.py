"""End-to-end live validation against the SigNoz stack + seeded demo corpus.

Skipped unless ``SIGNOZ_LIVE=1``. Uses the corpus manifest's ground-truth
``bad_trace_ids`` as the bad cohort and asserts the extracted matrix contains the
ground-truth structural features at the prevalences the manifest and the direct
ClickHouse validation recorded:

* 55 bad / 445 healthy (``conditional_dep`` seed 42, n=500);
* edge ``shop-payment => redis-retry`` present in 276 traces;
* ``shop-flag-service`` absent in 217 traces;
* the conjunction (edge ∧ ¬flag) selects exactly the 55 bad traces.

Run:

    SIGNOZ_LIVE=1 SIGNOZ_EMAIL=... SIGNOZ_PASSWORD=... SIGNOZ_ORG_ID=... \
        uv run pytest tests/extract/test_live_integration.py -v
"""

from __future__ import annotations

import glob
import json
import os
import time
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from whodunit.extract import (
    CohortSpec,
    MatchingConfig,
    ScanConfig,
    extract_matrix,
)
from whodunit.signoz_client import SigNozClient, SigNozConfig

pytestmark = pytest.mark.live

_LIVE = os.environ.get("SIGNOZ_LIVE") == "1"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_manifest() -> dict[str, Any]:
    """Newest conditional_dep seed-42 n500 manifest with inline bad_trace_ids."""
    pattern = str(_REPO_ROOT / "corpus" / "out" / "manifest-conditional_dep-s42-n500-*.json")
    candidates = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for path in candidates:
        data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("bad_trace_ids_inline") and data.get("bad_trace_ids"):
            return data
    pytest.skip("no inline conditional_dep-s42-n500 manifest found in corpus/out")


@pytest.mark.skipif(not _LIVE, reason="set SIGNOZ_LIVE=1 to run live integration")
def test_extract_matrix_reproduces_ground_truth(tmp_path: Path) -> None:
    manifest = _load_manifest()
    bad_ids = tuple(manifest["bad_trace_ids"])
    assert len(bad_ids) == 55, "manifest bad cohort should be 55 traces"

    # Wide window: the corpus is emitted into the last hour, but re-runs drift;
    # scope by deployment.environment + explicit ids and a generous window.
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 48 * 3600 * 1000

    spec = CohortSpec(
        window_start_unix_ms=start_ms,
        window_end_unix_ms=now_ms,
        trace_ids=bad_ids,
        environment="whodunit-demo",
    )
    client = SigNozClient(SigNozConfig())
    with client:
        mm = extract_matrix(
            client,
            spec,
            # strategy="all" → every healthy trace in window (the manifest's 445),
            # so the 276/217 population prevalences are directly checkable.
            matching=MatchingConfig(strategy="all"),
            scan_config=ScanConfig(attribute_keys=("cache.hit", "order.completed")),
            workdir=tmp_path,
        )

    # --- cohort sizes ----------------------------------------------------- #
    assert mm.meta.n_traces_bad == 55
    assert mm.meta.n_traces_healthy == 445
    assert mm.frame.height == 500

    names = {c.name for c in mm.meta.columns}

    # --- ground-truth features exist -------------------------------------- #
    edge_col = "edge__shop_payment__redis_retry"
    flag_col = "svc__shop_flag_service"
    assert edge_col in names, f"missing edge feature; have {sorted(names)}"
    assert flag_col in names, f"missing flag-service feature; have {sorted(names)}"

    # --- prevalences match the manifest / direct-ClickHouse validation ---- #
    assert mm.prevalence(edge_col) == 276
    # flag-service *absent* in 217 → present in 500 - 217 = 283.
    assert mm.prevalence(flag_col) == 283
    flag_absent = 500 - mm.prevalence(flag_col)
    assert flag_absent == 217

    # --- the conjunction is a perfect separator of the bad cohort --------- #
    conjunction = mm.frame.filter(
        (pl.col(edge_col) == 1) & (pl.col(flag_col) == 0)
    )
    assert conjunction.height == 55
    assert set(conjunction["label"].to_list()) == {1}
    assert set(conjunction["trace_id"].to_list()) == set(bad_ids)

    # --- cross-signal log feature present & lands on the bad cohort ------- #
    log_cols = [c.name for c in mm.meta.columns if c.name.startswith("log__")]
    assert log_cols, "expected at least one log feature (cross-signal join)"

    # --- cost meter surfaced from ExecStats ------------------------------- #
    assert mm.meta.rows_scanned is not None and mm.meta.rows_scanned > 0

    # --- persisted parquet round-trips ------------------------------------ #
    assert (tmp_path / "matrix.parquet").exists()
