"""In-memory trace model.

A trace is an abstract tree of :class:`SpanNode` built by :mod:`corpus.topology`,
then mutated by a fault in :mod:`corpus.faults`, then walked by
:mod:`corpus.emit` to produce real OTLP spans. Keeping the plan abstract means
faults are pure structural edits and the manifest ground truth can be derived
from the same tree the emitter sees.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpanNode:
    """One span in the abstract trace tree.

    Attributes
    ----------
    service:
        Logical service name *without* the ``shop-`` prefix.
    name:
        Span name (operation).
    kind:
        OTel span kind string: ``SERVER`` | ``CLIENT`` | ``INTERNAL``.
    tag:
        Stable structural marker used by faults and ground-truth specs, e.g.
        ``"flag-service"``, ``"redis-retry"``, ``"cache-get"``. ``None`` for
        ordinary spans.
    attrs:
        Span attributes (http.route, db.system, cache.hit, feature flags, ...).
    dur_mu / dur_sigma:
        Parameters of the log-normal duration distribution, in log-nanoseconds.
    error:
        Whether this span should carry ERROR status (only when --error-visible).
    children:
        Child span nodes.
    """

    service: str
    name: str
    kind: str = "INTERNAL"
    tag: str | None = None
    attrs: dict[str, object] = field(default_factory=dict)
    dur_mu: float = 15.0
    dur_sigma: float = 0.5
    error: bool = False
    children: list["SpanNode"] = field(default_factory=list)

    def add(self, child: "SpanNode") -> "SpanNode":
        self.children.append(child)
        return child

    def walk(self):
        """Pre-order iterator over (node)."""
        yield self
        for c in self.children:
            yield from c.walk()

    def count(self) -> int:
        return sum(1 for _ in self.walk())

    def has_tag(self, tag: str) -> bool:
        return any(n.tag == tag for n in self.walk())

    def has_service(self, service: str) -> bool:
        return any(n.service == service for n in self.walk())


@dataclass
class LogRecordPlan:
    """A log line to emit, carrying the trace/span id of its trace."""

    span_index: int  # which span in pre-order this log attaches to (for span_id)
    severity: str  # "INFO" | "WARN" | "ERROR"
    body: str
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass
class TracePlan:
    """A complete planned trace: the tree, its logs, and its ground truth."""

    trace_index: int
    root: SpanNode
    logs: list[LogRecordPlan] = field(default_factory=list)
    # Business/label outcome. ``bad`` is the mining label; how it is surfaced
    # (ERROR status vs order.completed=false) depends on --error-visible.
    bad: bool = False
    # Free-form structural tags describing why this trace is in its cohort;
    # aggregated into the manifest for auditing.
    cohort: str = "healthy"
    # Wall-clock start offset (ns) relative to the run's base time.
    start_offset_ns: int = 0
