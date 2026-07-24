"""Deterministic ID generation.

OTel would normally mint random trace/span IDs. We need the opposite: IDs that
are a pure function of ``(seed, trace_index, span_index)`` so that

  * the manifest's list of bad ``trace_id`` values is reproducible, and
  * logs can carry the exact ``trace_id`` of the trace they belong to, and
  * a re-run with the same seed lands identical IDs in ClickHouse.

We drive OTel's SDK through a single shared :class:`SeededIdGenerator` whose next
trace/span id is set explicitly right before each ``start_span`` call.
"""

from __future__ import annotations

import hashlib

from opentelemetry.sdk.trace.id_generator import IdGenerator


def _digest_int(*parts: object, nbytes: int) -> int:
    """A stable non-zero integer derived from the given parts."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    raw = hashlib.sha256(key).digest()[:nbytes]
    value = int.from_bytes(raw, "big")
    # Trace/span ids must be non-zero to be valid.
    return value or 1


def make_trace_id(seed: int, trace_index: int) -> int:
    """128-bit trace id (as int) for the given trace."""
    return _digest_int(seed, trace_index, "trace", nbytes=16)


def make_span_id(seed: int, trace_index: int, span_index: int) -> int:
    """64-bit span id (as int) for a span within a trace."""
    return _digest_int(seed, trace_index, "span", span_index, nbytes=8)


class SeededIdGenerator(IdGenerator):
    """An :class:`IdGenerator` that returns whatever id was last staged.

    A single instance is shared by every service's ``TracerProvider``. Before
    each ``start_span`` the emitter stages the exact ids it wants via
    :meth:`stage`. This is safe because emission is single-threaded.
    """

    def __init__(self) -> None:
        self._trace_id = make_trace_id(0, 0)
        self._span_id = make_span_id(0, 0, 0)

    def stage(self, trace_id: int, span_id: int) -> None:
        self._trace_id = trace_id
        self._span_id = span_id

    def stage_span(self, span_id: int) -> None:
        self._span_id = span_id

    def generate_span_id(self) -> int:
        return self._span_id

    def generate_trace_id(self) -> int:
        return self._trace_id
