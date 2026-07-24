"""Whodunit Stage 0/1 — cohort definition and the one-scan feature matrix.

Public API the CLI (Wave 3) calls:

* :func:`extract_matrix` — the one-call end-to-end entry point: resolve cohorts,
  run the one scan, materialise the polars matrix + metadata.
* :class:`CohortSpec`, :class:`MatchingConfig`, :func:`resolve_cohorts`,
  :class:`ResolvedCohorts` — Stage 0 cohort resolution / case-control matching.
* :class:`ScanConfig`, :func:`run_scan`, :class:`ScanResult` — Stage 1 scan.
* :func:`build_feature_matrix`, :func:`save_matrix`, :func:`load_matrix`,
  :class:`MaterializedMatrix`, :func:`virtual_negation` — materialisation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cohort import (
    CohortSpec,
    MatchingConfig,
    ResolvedCohorts,
    resolve_cohorts,
)
from .matrix import (
    MaterializedMatrix,
    build_feature_matrix,
    load_matrix,
    save_matrix,
    virtual_negation,
)
from .scan import ScanConfig, ScanResult, run_scan

if TYPE_CHECKING:
    from pathlib import Path

    from whodunit.signoz_client import SigNozClient

__all__ = [
    "CohortSpec",
    "MatchingConfig",
    "MaterializedMatrix",
    "ResolvedCohorts",
    "ScanConfig",
    "ScanResult",
    "build_feature_matrix",
    "extract_matrix",
    "load_matrix",
    "resolve_cohorts",
    "run_scan",
    "save_matrix",
    "virtual_negation",
]


def extract_matrix(
    client: SigNozClient,
    spec: CohortSpec,
    *,
    matching: MatchingConfig | None = None,
    scan_config: ScanConfig | None = None,
    workdir: str | Path | None = None,
    name: str = "matrix",
) -> MaterializedMatrix:
    """End-to-end Stage 0+1: cohorts → one scan → materialised matrix.

    If ``workdir`` is given the matrix is also persisted to parquet there.
    """
    cohorts = resolve_cohorts(client, spec, matching)
    scan = run_scan(
        client,
        bad_ids=cohorts.bad_ids,
        healthy_ids=cohorts.healthy_ids,
        window_start_unix_ms=spec.window_start_unix_ms,
        window_end_unix_ms=spec.window_end_unix_ms,
        environment=spec.environment,
        config=scan_config,
    )
    mm = build_feature_matrix(
        scan,
        n_traces_bad=len(cohorts.bad_ids),
        n_traces_healthy=len(cohorts.healthy_ids),
        matched_on=cohorts.matched_on,
        window_start_unix_ms=spec.window_start_unix_ms,
        window_end_unix_ms=spec.window_end_unix_ms,
        bad_cohort_filter=spec.ch_filter,
    )
    if workdir is not None:
        save_matrix(mm, workdir, name)
    return mm
