"""The compiler's small intermediate representation.

A mined :class:`~whodunit.types.Finding` is an *itemset* of feature names (some
prefixed ``NOT ``). Each feature resolves, through the
:class:`~whodunit.types.FeatureColumn` table, into a fragment of trace-operator
algebra:

* ``SPAN_PREDICATE`` -> a single :class:`Leaf` (one sibling builder query).
* ``EDGE`` (direct parent -> child) -> ``parent => child``.
* ``ANCESTOR`` (transitive) -> ``parent -> child``.

The operator mapping is the *empirically verified* one (see ``ENGINE-NOTES.md``
and ``Track2/probe-results/PROBES.md``): on v0.132.2 ``=>`` is the DIRECT
single-hop descendant and ``->`` is the INDIRECT any-depth descendant. The
prose in ``WHODUNIT-CONCEPT.md`` §4.5 has this pair flipped; the live engine and
this module do not.

The IR is deliberately tiny — literals, ``=>``, ``->``, ``&&``, ``||`` and a
trace-scoped unary ``NOT`` — with two invariants baked in by construction:

1. **Left-bias normalisation.** Positive (presence) fragments are folded to the
   left; negations are appended on the right. ``buildAndCTE`` returns the left
   operand's spans, so the outcome-bearing operand must be leftmost and
   ``returnSpansFrom`` names its leftmost leaf.
2. **Deterministic naming.** Leaves are named ``A, B, C, ...`` in a strict
   left-to-right (parent-before-child) walk, so the same finding always emits
   byte-identical envelopes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from whodunit.types import FeatureColumn, FeatureKind

# --------------------------------------------------------------------------- #
# Operator tokens (empirically verified on v0.132.2 — see ENGINE-NOTES.md)
# --------------------------------------------------------------------------- #

OP_DIRECT = "=>"
"""Direct, single-hop descendant (EDGE features)."""
OP_INDIRECT = "->"
"""Indirect, any-depth descendant (ANCESTOR features)."""
OP_AND = "&&"
OP_OR = "||"

MAX_TRACE_OPERATORS = 10
"""``MaxTraceOperators`` in the generator — expressions above this are refused."""

_NOT_PREFIX = "NOT "

_NAME_KEY = "duration_nano"  # raw span duration column (verified via raw probe)


# --------------------------------------------------------------------------- #
# IR node types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Leaf:
    """A named reference to a sibling trace-signal builder query.

    ``filter_expr`` is a v5 filter expression (``service.name = 'x' AND ...``).
    ``name`` is assigned during :func:`allocate_names` and matches
    ``^[A-Za-z][A-Za-z0-9_]*$``.
    """

    filter_expr: str
    description: str = ""
    name: str = ""


@dataclass(frozen=True)
class Not:
    """Trace-scoped unary negation (``GLOBAL NOT IN`` over trace_ids)."""

    child: IRNode


@dataclass(frozen=True)
class BinOp:
    """A binary operator node (``=>``, ``->``, ``&&``, ``||``)."""

    op: str
    left: IRNode
    right: IRNode


IRNode = Leaf | Not | BinOp


# --------------------------------------------------------------------------- #
# Result of building an IR from a finding
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ParsedItem:
    """One entry of a finding's itemset, resolved against the column table."""

    negated: bool
    column: FeatureColumn
    raw: str


@dataclass(frozen=True)
class IRBuild:
    """Either a compilable IR tree or a structured reason it cannot be built."""

    root: IRNode | None
    return_spans_from: str
    leaves: tuple[Leaf, ...] = field(default_factory=tuple)
    refusal_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.root is not None and self.refusal_reason is None


# --------------------------------------------------------------------------- #
# Feature name parsing
# --------------------------------------------------------------------------- #


def parse_item(raw: str, columns: dict[str, FeatureColumn]) -> ParsedItem | None:
    """Resolve one itemset entry (possibly ``NOT ``-prefixed) to a column."""
    negated = raw.startswith(_NOT_PREFIX)
    key = raw[len(_NOT_PREFIX) :] if negated else raw
    col = columns.get(key)
    if col is None:
        return None
    return ParsedItem(negated=negated, column=col, raw=raw)


# --------------------------------------------------------------------------- #
# Filter-expression construction (safe, validated against a vocabulary)
# --------------------------------------------------------------------------- #


def _quote(value: str) -> str:
    """Single-quote a literal, escaping embedded quotes (ClickHouse style)."""
    return "'" + value.replace("'", "''") + "'"


def build_filter_expr(
    col: FeatureColumn,
    *,
    vocabulary: frozenset[str] | None = None,
) -> str:
    """Build a v5 filter expression for a span-predicate-like column.

    Keys are validated against ``vocabulary`` when provided; an unknown key
    raises :class:`ValueError` so a typo can never silently widen a query.
    """
    clauses: list[str] = []

    def _check(key: str) -> None:
        if vocabulary is not None and key not in vocabulary:
            raise ValueError(f"attribute key {key!r} not in provided vocabulary")

    if col.service_name is not None:
        _check("service.name")
        clauses.append(f"service.name = {_quote(col.service_name)}")
    if col.span_name is not None:
        _check("name")
        clauses.append(f"name = {_quote(col.span_name)}")
    if col.status is not None:
        _check("status")
        clauses.append(f"status = {_quote(col.status)}")
    if col.duration_ge_ns is not None:
        _check(_NAME_KEY)
        clauses.append(f"{_NAME_KEY} >= {int(col.duration_ge_ns)}")
    if col.duration_lt_ns is not None:
        _check(_NAME_KEY)
        clauses.append(f"{_NAME_KEY} < {int(col.duration_lt_ns)}")

    if not clauses:
        raise ValueError(f"column {col.name!r} carries no compilable predicate")
    return " AND ".join(clauses)


# --------------------------------------------------------------------------- #
# Tree helpers
# --------------------------------------------------------------------------- #


def iter_leaves(node: IRNode) -> Iterator[Leaf]:
    """Yield leaves left-to-right (parent before child, positive before NOT)."""
    if isinstance(node, Leaf):
        yield node
    elif isinstance(node, Not):
        yield from iter_leaves(node.child)
    else:
        yield from iter_leaves(node.left)
        yield from iter_leaves(node.right)


def leftmost_leaf(node: IRNode) -> Leaf:
    """The leaf whose spans ``returnSpansFrom`` should name (left-bias)."""
    return next(iter_leaves(node))


def count_operators(node: IRNode) -> int:
    """Count operator nodes (each ``BinOp`` and each ``NOT``)."""
    if isinstance(node, Leaf):
        return 0
    if isinstance(node, Not):
        return 1 + count_operators(node.child)
    return 1 + count_operators(node.left) + count_operators(node.right)


def allocate_names(node: IRNode) -> IRNode:
    """Return a copy of ``node`` with leaves named ``A, B, C, ...`` in DFS order."""
    counter = _NameAllocator()

    def _walk(n: IRNode) -> IRNode:
        if isinstance(n, Leaf):
            return Leaf(filter_expr=n.filter_expr, description=n.description, name=counter.next())
        if isinstance(n, Not):
            return Not(child=_walk(n.child))
        # Preserve left-to-right order so naming is deterministic.
        left = _walk(n.left)
        right = _walk(n.right)
        return BinOp(op=n.op, left=left, right=right)

    return _walk(node)


class _NameAllocator:
    """Yields ``A, B, ... Z, AA, AB, ...`` — spreadsheet-column style."""

    def __init__(self) -> None:
        self._i = 0

    def next(self) -> str:
        n = self._i
        self._i += 1
        chars: list[str] = []
        while True:
            chars.append(chr(ord("A") + (n % 26)))
            n = n // 26 - 1
            if n < 0:
                break
        return "".join(reversed(chars))


# --------------------------------------------------------------------------- #
# The fragment builder: one feature column -> an IR fragment
# --------------------------------------------------------------------------- #


def _fragment_for(col: FeatureColumn, *, vocabulary: frozenset[str] | None) -> IRNode:
    """Build the (unnamed) IR fragment for a single positive feature column."""
    if col.kind is FeatureKind.SPAN_PREDICATE:
        return Leaf(filter_expr=build_filter_expr(col, vocabulary=vocabulary), description=col.name)
    if col.kind in (FeatureKind.EDGE, FeatureKind.ANCESTOR):
        if col.edge_parent is None or col.edge_child is None:
            raise ValueError(f"{col.kind} column {col.name!r} missing edge_parent/edge_child")
        parent = Leaf(
            filter_expr=_edge_side_expr(col.edge_parent, vocabulary),
            description=f"{col.name}::parent",
        )
        child = Leaf(
            filter_expr=_edge_side_expr(col.edge_child, vocabulary),
            description=f"{col.name}::child",
        )
        op = OP_DIRECT if col.kind is FeatureKind.EDGE else OP_INDIRECT
        return BinOp(op=op, left=parent, right=child)
    raise ValueError(f"column kind {col.kind} is not compilable into trace operators")


SPAN_ENDPOINT_PREFIX = "span:"
"""Sentinel on an edge endpoint selecting a span-*name* match instead of a service.

``FeatureColumn.edge_parent`` / ``edge_child`` are documented as a *service pair*
(``service.name = '...'``, the default). Real discriminators sometimes terminate
on a specific span (e.g. ``shop-payment => redis-retry`` where ``redis-retry`` is
a span name, not a service). Prefix such an endpoint with ``span:`` and the
compiler matches ``name = '...'`` instead. This keeps the plain service-pair
contract intact while making service->span edges expressible.
"""


def _edge_side_expr(endpoint: str, vocabulary: frozenset[str] | None) -> str:
    """Build an edge-endpoint predicate: ``service.name`` by default, ``name``
    when the endpoint carries the :data:`SPAN_ENDPOINT_PREFIX` sentinel."""
    if endpoint.startswith(SPAN_ENDPOINT_PREFIX):
        key, value = "name", endpoint[len(SPAN_ENDPOINT_PREFIX) :]
    else:
        key, value = "service.name", endpoint
    if vocabulary is not None and key not in vocabulary:
        raise ValueError(f"attribute key {key!r} not in provided vocabulary")
    return f"{key} = {_quote(value)}"
