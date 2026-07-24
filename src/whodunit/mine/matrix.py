"""Internal boolean-matrix representation shared across the mining stages.

The public :func:`whodunit.mine.mine` entry point takes a polars ``DataFrame``
(``trace_id``, ``label: bool``, plus boolean feature columns) and a list of
:class:`~whodunit.types.FeatureColumn`. This module lowers that frame into a
column-oriented bitset representation that every downstream stage (FP-growth,
statistics, bootstrap) reasons over. Bitsets make support counting exact and
deterministic: the support of an itemset is a bitwise AND followed by a
popcount.

By convention ``label == True`` is the **bad** cohort and ``label == False`` is
the matched **healthy** cohort. Absence features are materialised here as
complement bitsets named ``"NOT <name>"`` so the rest of the pipeline treats
presence and absence items uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from whodunit.types import FeatureColumn

NOT_PREFIX = "NOT "


def complement_name(feature_name: str) -> str:
    """The itemset token for the absence of ``feature_name``."""
    return f"{NOT_PREFIX}{feature_name}"


def is_negation(item: str) -> bool:
    """Whether an itemset token denotes an absence (complement) feature."""
    return item.startswith(NOT_PREFIX)


def base_name(item: str) -> str:
    """Strip the ``NOT `` prefix from an absence token; identity for presence."""
    return item[len(NOT_PREFIX) :] if is_negation(item) else item


@dataclass(frozen=True)
class FeatureData:
    """Column-oriented, bitset-backed view of the trace x feature matrix.

    Every item (presence feature name, or ``"NOT <name>"`` complement) maps to a
    Python ``int`` used as a bitset over the ``n`` rows: bit ``i`` is set iff the
    item is true for row ``i``. ``label_bad`` / ``label_healthy`` are the cohort
    bitsets. ``all_bad`` / ``all_healthy`` are the full-cohort masks used as
    denominators and popcount helpers.
    """

    n: int
    n_bad: int
    n_healthy: int
    items: tuple[str, ...]
    """All minable items, presence first then complements, in stable order."""
    bitsets: dict[str, int]
    label_bad: int
    label_healthy: int
    columns_by_name: dict[str, FeatureColumn]
    span_negation_items: frozenset[str]
    """Complement items whose parent has ``requires_span_level_negation``."""

    def support(self, itemset: frozenset[str]) -> int:
        """Rows (over the whole matrix) matching every item in ``itemset``."""
        mask = (1 << self.n) - 1
        for item in itemset:
            mask &= self.bitsets[item]
        return mask.bit_count()

    def cohort_mask(self, itemset: frozenset[str]) -> int:
        """The row bitset matching every item in ``itemset``."""
        mask = (1 << self.n) - 1
        for item in itemset:
            mask &= self.bitsets[item]
        return mask

    def contingency(self, itemset: frozenset[str]) -> tuple[int, int, int, int]:
        """The 2x2 table ``(a, b, c, d)`` against the label.

        ``a`` present&bad, ``b`` present&healthy, ``c`` absent&bad,
        ``d`` absent&healthy.
        """
        present = self.cohort_mask(itemset)
        a = (present & self.label_bad).bit_count()
        b = (present & self.label_healthy).bit_count()
        c = self.n_bad - a
        d = self.n_healthy - b
        return a, b, c, d


def build_feature_data(
    frame: pl.DataFrame,
    columns: list[FeatureColumn],
    *,
    label_column: str = "label",
) -> FeatureData:
    """Lower a polars frame + column metadata into a :class:`FeatureData`.

    Only columns listed in ``columns`` are treated as features; the frame may
    carry extra bookkeeping columns (e.g. ``trace_id``) which are ignored. Each
    presence feature gets a complement item ``"NOT <name>"`` automatically.
    """
    if label_column not in frame.columns:
        raise ValueError(f"frame is missing the {label_column!r} column")

    missing = [c.name for c in columns if c.name not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing feature columns: {missing}")

    n = frame.height
    full_mask = (1 << n) - 1

    label_series = frame.get_column(label_column)
    if label_series.dtype != pl.Boolean:
        raise TypeError(f"{label_column!r} column must be Boolean, got {label_series.dtype}")
    label_bad = _column_to_bitset(label_series)
    label_healthy = full_mask & ~label_bad

    bitsets: dict[str, int] = {}
    items: list[str] = []
    complements: list[str] = []
    span_negation: set[str] = set()
    columns_by_name: dict[str, FeatureColumn] = {}

    for col in columns:
        series = frame.get_column(col.name)
        if series.dtype != pl.Boolean:
            raise TypeError(f"feature {col.name!r} must be Boolean, got {series.dtype}")
        present = _column_to_bitset(series)
        bitsets[col.name] = present
        items.append(col.name)
        columns_by_name[col.name] = col

        comp = complement_name(col.name)
        bitsets[comp] = full_mask & ~present
        complements.append(comp)
        if col.requires_span_level_negation:
            span_negation.add(comp)

    ordered_items = tuple(items) + tuple(complements)

    return FeatureData(
        n=n,
        n_bad=label_bad.bit_count(),
        n_healthy=label_healthy.bit_count(),
        items=ordered_items,
        bitsets=bitsets,
        label_bad=label_bad,
        label_healthy=label_healthy,
        columns_by_name=columns_by_name,
        span_negation_items=frozenset(span_negation),
    )


def _column_to_bitset(series: pl.Series) -> int:
    """Pack a boolean polars series into a big-integer bitset (bit i = row i)."""
    acc = 0
    for i, val in enumerate(series):
        if val:
            acc |= 1 << i
    return acc
