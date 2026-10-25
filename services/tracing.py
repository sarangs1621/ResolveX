"""OpenTelemetry Distributed Tracing Service.

Instruments the agent request lifecycle:
- cache.lookup
- rag.retrieval
- llm.generation
- tool.execution
- crm.persistence

Provides OpenTelemetry standard tracer with OTLP exporter support (Jaeger, Datadog)
and an in-memory trace inspection buffer for instant observability without external daemons.
"""
from __future__ import annotations
import collections
import contextlib
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("support_agent.tracing")

# Try importing opentelemetry; fallback gracefully if not installed
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": "resolvex-agent", "service.version": "3.0.0"})
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    otel_tracer = trace.get_tracer("resolvex.support.agent", "3.0.0")
    HAS_OTEL = True
except Exception as err:
    logger.info(f"OpenTelemetry SDK not initialized ({err}). Using lightweight tracer.")
    otel_tracer = None
    HAS_OTEL = False


class TraceSpanRecord:
    def __init__(self, name: str, trace_id: str, parent_id: Optional[str] = None):
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.attributes: Dict[str, Any] = {}
        self.status: str = "OK"

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def finish(self, status: str = "OK"):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "start_time": self.start_time
        }


class DistributedTracingService:
    def __init__(self):
        # Ring buffer storing the last 100 traces
        self.recent_traces: collections.deque = collections.deque(maxlen=100)
        self._current_traces: Dict[str, List[TraceSpanRecord]] = {}

    def new_trace_id(self) -> str:
        return f"trc_{uuid.uuid4().hex[:16]}"

    @contextlib.contextmanager
    def span(self, name: str, trace_id: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None):
        """Context manager for instrumenting code blocks with timing & attributes."""
        tid = trace_id or self.new_trace_id()
        record = TraceSpanRecord(name=name, trace_id=tid)
        if attributes:
            for k, v in attributes.items():
                record.set_attribute(k, v)

        if tid not in self._current_traces:
            self._current_traces[tid] = []
        self._current_traces[tid].append(record)

        # Also trigger OTel span if available
        otel_ctx = None
        if HAS_OTEL and otel_tracer:
            try:
                otel_ctx = otel_tracer.start_as_current_span(name)
                otel_ctx.__enter__()
            except Exception:
                pass

        try:
            yield record
            record.finish("OK")
        except Exception as err:
            record.set_attribute("error.message", str(err))
            record.finish("ERROR")
            raise
        finally:
            if otel_ctx:
                try:
                    otel_ctx.__exit__(None, None, None)
                except Exception:
                    pass

    def finalize_trace(self, trace_id: str, meta: Optional[Dict[str, Any]] = None):
        """Archives a completed trace into the inspection ring buffer."""
        spans = self._current_traces.pop(trace_id, [])
        if not spans:
            return

        total_duration = sum(s.duration_ms for s in spans)
        trace_bundle = {
            "trace_id": trace_id,
            "timestamp": spans[0].start_time,
            "total_duration_ms": round(total_duration, 2),
            "span_count": len(spans),
            "meta": meta or {},
            "spans": [s.to_dict() for s in spans]
        }
        self.recent_traces.appendleft(trace_bundle)

    def get_recent_traces(self, limit: int = 25) -> List[Dict[str, Any]]:
        return list(self.recent_traces)[:limit]


# Global singleton tracer
tracer = DistributedTracingService()
