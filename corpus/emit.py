"""OTLP emission.

Every logical service gets its own ``TracerProvider`` and ``LoggerProvider``
with a distinct ``service.name`` resource (all prefixed ``shop-`` and tagged
``deployment.environment=whodunit-demo``), but they share one process and one
deterministic :class:`SeededIdGenerator`. A trace plan is walked in pre-order;
span and trace ids are staged explicitly before each ``start_span`` so the exact
ids are reproducible and match the ids carried by the trace's logs.
"""

from __future__ import annotations

import math
import random

from opentelemetry._logs import LogRecord as ApiLogRecord
from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    SpanKind,
    Status,
    StatusCode,
    TraceFlags,
    set_span_in_context,
)

from . import DEPLOYMENT_ENVIRONMENT, SERVICE_PREFIX, SERVICES
from .ids import SeededIdGenerator, make_span_id, make_trace_id
from .model import SpanNode, TracePlan

_KIND = {
    "SERVER": SpanKind.SERVER,
    "CLIENT": SpanKind.CLIENT,
    "INTERNAL": SpanKind.INTERNAL,
    "PRODUCER": SpanKind.PRODUCER,
    "CONSUMER": SpanKind.CONSUMER,
}

_SEV = {
    "INFO": (SeverityNumber.INFO, "INFO"),
    "WARN": (SeverityNumber.WARN, "WARN"),
    "ERROR": (SeverityNumber.ERROR, "ERROR"),
}

_SAMPLED = TraceFlags(TraceFlags.SAMPLED)


class Emitter:
    """Holds per-service providers and emits planned traces to OTLP/HTTP."""

    def __init__(self, endpoint: str, seed: int) -> None:
        base = endpoint.rstrip("/")
        self._seed = seed
        self._idgen = SeededIdGenerator()
        self._tracers = {}
        self._loggers = {}
        self._span_processors = []
        self._log_processors = []

        for svc in SERVICES:
            resource = Resource.create(
                {
                    "service.name": f"{SERVICE_PREFIX}{svc}",
                    "deployment.environment": DEPLOYMENT_ENVIRONMENT,
                    "telemetry.sdk.language": "python",
                    "whodunit.corpus": True,
                }
            )
            tp = TracerProvider(resource=resource, id_generator=self._idgen)
            sp = BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{base}/v1/traces"),
                max_queue_size=8192,
                max_export_batch_size=1024,
            )
            tp.add_span_processor(sp)
            self._span_processors.append(sp)
            self._tracers[svc] = tp.get_tracer("whodunit.corpus")

            lp = LoggerProvider(resource=resource)
            lproc = BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{base}/v1/logs"),
                max_queue_size=8192,
                max_export_batch_size=1024,
            )
            lp.add_log_record_processor(lproc)
            self._log_processors.append(lproc)
            self._loggers[svc] = lp.get_logger("whodunit.corpus")

    # --------------------------------------------------------------------- #
    def emit_trace(self, plan: TracePlan, base_time_ns: int) -> str:
        """Emit all spans + logs of a plan. Returns the hex trace_id."""
        trace_id = make_trace_id(self._seed, plan.trace_index)
        # Assign a stable pre-order index to every node for span-id derivation.
        nodes = list(plan.root.walk())
        span_ids = {
            id(n): make_span_id(self._seed, plan.trace_index, i) for i, n in enumerate(nodes)
        }
        t0 = base_time_ns + plan.start_offset_ns
        rng = random.Random(f"{self._seed}:{plan.trace_index}:time")

        self._emit_node(plan.root, trace_id, None, span_ids, t0, rng)

        # Logs carry the trace_id (and the span_id of their attach point).
        node_by_index = nodes
        for lr in plan.logs:
            idx = min(lr.span_index, len(node_by_index) - 1)
            span_id = span_ids[id(node_by_index[idx])]
            self._emit_log(node_by_index[idx].service, lr, trace_id, span_id, t0)

        return f"{trace_id:032x}"

    def _emit_node(self, node: SpanNode, trace_id, parent_span_id, span_ids, start_ns, rng) -> int:
        span_id = span_ids[id(node)]
        # Parent context: root has none; children reference their parent span.
        if parent_span_id is None:
            ctx = None
        else:
            parent_ctx = SpanContext(
                trace_id=trace_id,
                span_id=parent_span_id,
                is_remote=False,
                trace_flags=_SAMPLED,
            )
            ctx = set_span_in_context(NonRecordingSpan(parent_ctx))

        self._idgen.stage(trace_id, span_id)
        own_dur = _lognormal_ns(rng, node.dur_mu, node.dur_sigma)

        tracer = self._tracers[node.service]
        span = tracer.start_span(
            node.name,
            context=ctx,
            kind=_KIND.get(node.kind, SpanKind.INTERNAL),
            start_time=start_ns,
            attributes={k: _attr(v) for k, v in node.attrs.items()},
        )
        if node.error:
            span.set_status(Status(StatusCode.ERROR, "fault"))

        # Lay children out sequentially inside this span.
        cursor = start_ns + max(1, own_dur // 20)
        for child in node.children:
            child_end = self._emit_node(child, trace_id, span_id, span_ids, cursor, rng)
            cursor = child_end + max(1, own_dur // 40)
        end_ns = max(start_ns + own_dur, cursor)
        span.end(end_time=end_ns)
        return end_ns

    def _emit_log(self, service, lr, trace_id, span_id, ts_ns) -> None:
        sev_num, sev_text = _SEV.get(lr.severity, _SEV["INFO"])
        record = ApiLogRecord(
            timestamp=ts_ns,
            observed_timestamp=ts_ns,
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=_SAMPLED,
            severity_number=sev_num,
            severity_text=sev_text,
            body=lr.body,
            attributes={k: _attr(v) for k, v in lr.attributes.items()},
        )
        self._loggers[service].emit(record)

    def shutdown(self) -> None:
        for sp in self._span_processors:
            sp.force_flush()
            sp.shutdown()
        for lp in self._log_processors:
            lp.force_flush()
            lp.shutdown()


def _lognormal_ns(rng: random.Random, mu: float, sigma: float) -> int:
    return max(1000, int(math.exp(rng.gauss(mu, sigma))))


def _attr(v: object):
    """Coerce to an OTLP-legal attribute value."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)):
        return v
    return str(v)
