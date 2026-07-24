"""Stage 1 (cont.) — materialise the scan into a polars boolean matrix.

Turns a :class:`~whodunit.extract.scan.ScanResult` into:

* a **polars ``DataFrame``** — one row per ``trace_id``, an ``i8``/bool ``label``
  column, and one boolean column per feature; and
* a :class:`~whodunit.types.FeatureMatrix` metadata record carrying the column
  descriptors, cohort sizes, matched-on axes, window, and the ExecStats cost
  meter (with the cached-bucket over-report caveat documented on
  :func:`build_feature_matrix`).

The DataFrame is saved/loaded as parquet under a workdir; the metadata rides
alongside as JSON so a later stage can reconstruct the full picture.

**Absence encoding.** Every presence column implies a virtual ``NOT <name>``
complement. We do *not* materialise the complement columns — the miner
complements a boolean column for free — but the semantics differ per feature and
that difference is load-bearing for the compiler:

* **trace-scoped** complements (``NOT`` an existence feature — service, span
  name, edge, ancestor, log) mean *"this pattern appears nowhere in the trace"*.
  SigNoz's trace-operator ``NOT`` is itself trace-scoped, so these are
  **compiler-safe**.
* **span-scoped** complements (``NOT`` a duration-bucket or attribute-value
  feature) carry the reading *"this span type is present but that particular
  span lacks the property"* — e.g. *"a payment span exists but is not slow"*.
  The trace-scoped ``NOT`` cannot express this soundly, so those columns are
  marked ``requires_span_level_negation=True`` and the compiler must refuse to
  complement them. :func:`virtual_negation` exposes both the name and this flag
  so the miner can decide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from whodunit.types import FeatureColumn, FeatureMatrix

from .scan import ScanResult


@dataclass(frozen=True)
class MaterializedMatrix:
    """The polars body + its :class:`FeatureMatrix` metadata, together."""

    frame: pl.DataFrame
    meta: FeatureMatrix

    @property
    def feature_names(self) -> list[str]:
        return [c.name for c in self.meta.columns]

    def prevalence(self, feature: str, *, cohort: str = "all") -> int:
        """Count of traces where ``feature`` is 1, optionally within a cohort."""
        df = self.frame
        if cohort == "bad":
            df = df.filter(pl.col("label") == 1)
        elif cohort == "healthy":
            df = df.filter(pl.col("label") == 0)
        return int(df.select(pl.col(feature)).sum().item())


def build_feature_matrix(
    scan: ScanResult,
    *,
    n_traces_bad: int,
    n_traces_healthy: int,
    matched_on: list[str] | tuple[str, ...] = (),
    window_start_unix_ms: int | None = None,
    window_end_unix_ms: int | None = None,
    bad_cohort_filter: str | None = None,
) -> MaterializedMatrix:
    """Assemble the polars frame + :class:`FeatureMatrix` metadata.

    ExecStats caveat (surfaced verbatim into the metadata): SigNoz's
    ``bucket_cache.mergeBuckets`` sums stats from *cached* buckets into
    ExecStats, so ``rows_scanned``/``bytes_scanned`` can over-report the actual
    ClickHouse work when buckets are warm. They are a cost meter, not a bill.
    """
    feature_names = [c.name for c in scan.columns]
    schema: dict[str, pl.DataType] = {"trace_id": pl.Utf8(), "label": pl.Int8()}
    for name in feature_names:
        schema[name] = pl.Int8()

    if scan.rows:
        frame = pl.DataFrame(scan.rows).select(
            [pl.col(c).cast(t) for c, t in schema.items()]
        )
    else:
        frame = pl.DataFrame(schema=schema)

    meta = FeatureMatrix(
        columns=list(scan.columns),
        n_traces_bad=n_traces_bad,
        n_traces_healthy=n_traces_healthy,
        matched_on=list(matched_on),
        window_start_unix_ms=window_start_unix_ms,
        window_end_unix_ms=window_end_unix_ms,
        bad_cohort_filter=bad_cohort_filter,
        rows_scanned=scan.exec_stats.rows_scanned,
        bytes_scanned=scan.exec_stats.bytes_scanned,
        duration_ms=scan.exec_stats.duration_ms,
    )
    return MaterializedMatrix(frame=frame, meta=meta)


def virtual_negation(column: FeatureColumn) -> tuple[str, bool]:
    """Return the virtual complement column name and whether it needs span-level
    negation (i.e. the compiler must refuse it). See module docstring."""
    return (f"NOT {column.name}", column.requires_span_level_negation)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def save_matrix(mm: MaterializedMatrix, workdir: str | Path, name: str = "matrix") -> Path:
    """Write ``<workdir>/<name>.parquet`` + ``<name>.meta.json``. Returns the
    parquet path."""
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    parquet_path = wd / f"{name}.parquet"
    meta_path = wd / f"{name}.meta.json"
    mm.frame.write_parquet(parquet_path)
    meta_path.write_text(mm.meta.model_dump_json(indent=2), encoding="utf-8")
    return parquet_path


def load_matrix(workdir: str | Path, name: str = "matrix") -> MaterializedMatrix:
    """Reload a matrix saved by :func:`save_matrix`."""
    wd = Path(workdir)
    frame = pl.read_parquet(wd / f"{name}.parquet")
    meta_raw = json.loads((wd / f"{name}.meta.json").read_text(encoding="utf-8"))
    meta = FeatureMatrix.model_validate(meta_raw)
    return MaterializedMatrix(frame=frame, meta=meta)
