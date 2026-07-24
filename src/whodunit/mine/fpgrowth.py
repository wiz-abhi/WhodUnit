"""FP-growth over the boolean feature matrix.

Enumerates every frequent itemset (singles, conjunctions, and absences) up to
size ``k`` whose support in the **bad cohort** clears ``min_support``. Absence
features are the complement columns materialised in :mod:`whodunit.mine.matrix`
(``"NOT <name>"``): each bad-cohort row contributes exactly one item per feature
(the presence token if the feature is true, else the absence token), so a
transaction has one item per feature and the lattice is symmetric in
presence/absence.

The family enumerated here is *fixed before any statistical test runs* — that
ordering is what makes the downstream Benjamini-Hochberg FDR control valid, and
:func:`enumerate_family` is the single choke point that guarantees it.

The implementation is a classic FP-tree (frequent-pattern tree) with
conditional pattern-base mining, bounded by ``max_len``. It is deterministic:
the header table orders items by ``(descending support, item name)`` so ties
never depend on dict iteration order. A brute-force reference
(:func:`brute_force_family`) cross-checks it in the test suite.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import combinations

from whodunit.mine.matrix import FeatureData


@dataclass
class _FPNode:
    item: str | None
    parent: _FPNode | None
    count: int = 0
    children: dict[str, _FPNode] = field(default_factory=dict)
    node_link: _FPNode | None = None


def _transactions_from_bad_cohort(data: FeatureData) -> list[tuple[str, ...]]:
    """One transaction per bad-cohort row: the items true for that row.

    Emitted in ``data.items`` order (presence features, then complements) so the
    tree build is deterministic before the header re-sort.
    """
    transactions: list[tuple[str, ...]] = []
    bad_mask = data.label_bad
    for i in range(data.n):
        if not (bad_mask >> i) & 1:
            continue
        row_items = tuple(item for item in data.items if (data.bitsets[item] >> i) & 1)
        transactions.append(row_items)
    return transactions


def _order_key(item: str, support: dict[str, int]) -> tuple[int, str]:
    # Descending support, then ascending name -> total, deterministic order.
    return (-support[item], item)


class _FPTree:
    """An FP-tree plus its header table (item -> first node in the node-link)."""

    def __init__(self) -> None:
        self.root = _FPNode(item=None, parent=None)
        self.headers: dict[str, _FPNode] = {}

    def add(self, ordered_items: list[str], count: int) -> None:
        node = self.root
        for item in ordered_items:
            child = node.children.get(item)
            if child is None:
                child = _FPNode(item=item, parent=node, count=count)
                node.children[item] = child
                self._link(item, child)
            else:
                child.count += count
            node = child

    def _link(self, item: str, node: _FPNode) -> None:
        head = self.headers.get(item)
        if head is None:
            self.headers[item] = node
            return
        while head.node_link is not None:
            head = head.node_link
        head.node_link = node


def _build_tree(
    transactions: Iterable[tuple[tuple[str, ...], int]],
    min_count: int,
) -> tuple[_FPTree | None, dict[str, int]]:
    """Build an FP-tree from ``(items, count)`` transactions, pruning infrequent
    single items. Returns ``(tree, support)`` or ``(None, {})`` if empty."""
    support: dict[str, int] = {}
    materialised = list(transactions)
    for items, count in materialised:
        for item in items:
            support[item] = support.get(item, 0) + count
    frequent = {item: s for item, s in support.items() if s >= min_count}
    if not frequent:
        return None, {}

    tree = _FPTree()
    for items, count in materialised:
        ordered = [item for item in items if item in frequent]
        ordered.sort(key=lambda it: _order_key(it, frequent))
        if ordered:
            tree.add(ordered, count)
    return tree, frequent


def _conditional_base(node: _FPNode) -> list[tuple[tuple[str, ...], int]]:
    """The conditional pattern base for one header item: prefix paths + counts."""
    base: list[tuple[tuple[str, ...], int]] = []
    current: _FPNode | None = node
    while current is not None:
        path: list[str] = []
        ancestor = current.parent
        while ancestor is not None and ancestor.item is not None:
            path.append(ancestor.item)
            ancestor = ancestor.parent
        if path:
            path.reverse()
            base.append((tuple(path), current.count))
        current = current.node_link
    return base


def _mine(
    tree: _FPTree,
    support: dict[str, int],
    suffix: frozenset[str],
    min_count: int,
    max_len: int,
    out: dict[frozenset[str], int],
) -> None:
    # Process header items in a deterministic order (ascending support, name).
    for item in sorted(support, key=lambda it: (support[it], it)):
        new_set = suffix | {item}
        out[new_set] = support[item]
        if len(new_set) >= max_len:
            continue
        head = tree.headers.get(item)
        if head is None:
            continue
        cond_base = _conditional_base(head)
        cond_tree, cond_support = _build_tree(cond_base, min_count)
        if cond_tree is not None:
            _mine(cond_tree, cond_support, new_set, min_count, max_len, out)


def enumerate_family(
    data: FeatureData, min_support: int, max_len: int
) -> dict[frozenset[str], int]:
    """Enumerate all frequent itemsets (size 1..``max_len``) whose bad-cohort
    support is at least ``min_support``. Support counts are over the bad cohort.

    This is *the* family-fixing choke point for BH-FDR validity: everything
    returned here is decided with zero reference to the outcome-vs-label test.
    """
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    if min_support < 1:
        raise ValueError("min_support must be >= 1")

    transactions = _transactions_from_bad_cohort(data)
    tree, support = _build_tree(((t, 1) for t in transactions), min_support)
    out: dict[frozenset[str], int] = {}
    if tree is not None:
        _mine(tree, support, frozenset(), min_support, max_len, out)
    return out


def brute_force_family(
    data: FeatureData, min_support: int, max_len: int
) -> dict[frozenset[str], int]:
    """Reference enumeration: every item combination up to ``max_len``, counted
    directly over the bad cohort. Exponential — for tests/cross-checks only."""
    transactions = _transactions_from_bad_cohort(data)
    out: dict[frozenset[str], int] = {}
    for size in range(1, max_len + 1):
        for combo in combinations(data.items, size):
            combo_set = frozenset(combo)
            count = 0
            for txn in transactions:
                if combo_set.issubset(txn):
                    count += 1
            if count >= min_support:
                out[combo_set] = count
    return out
