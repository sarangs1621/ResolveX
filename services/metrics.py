"""Metrics, Telemetry & Observability Service."""
from __future__ import annotations
import time
from collections import Counter
from typing import Dict, List


class MetricsCollector:
    def __init__(self):
        self.start_time = time.time()
        self.total_requests = 0
        self.total_errors = 0
        self.status_codes: Counter = Counter()
        self.endpoint_hits: Counter = Counter()
        self.latencies_ms: List[float] = []
        self.tool_usage: Counter = Counter()

    def record_request(self, endpoint: str, status_code: int, duration_ms: float):
        self.total_requests += 1
        self.status_codes[str(status_code)] += 1
        self.endpoint_hits[endpoint] += 1
        if status_code >= 400:
            self.total_errors += 1
        self.latencies_ms.append(round(duration_ms, 2))
        if len(self.latencies_ms) > 1000:
            self.latencies_ms = self.latencies_ms[-1000:]

    def record_tool_call(self, tool_name: str):
        self.tool_usage[tool_name] += 1

    def get_metrics(self) -> dict:
        uptime = round(time.time() - self.start_time, 1)
        count = len(self.latencies_ms)
        if count > 0:
            avg_latency = round(sum(self.latencies_ms) / count, 2)
            sorted_lat = sorted(self.latencies_ms)
            p95_idx = int(0.95 * count)
            p95_latency = sorted_lat[min(p95_idx, count - 1)]
        else:
            avg_latency = 0.0
            p95_latency = 0.0

        error_rate = round((self.total_errors / self.total_requests * 100), 2) if self.total_requests > 0 else 0.0

        return {
            "uptime_seconds": uptime,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate_pct": error_rate,
            "latency": {
                "avg_ms": avg_latency,
                "p95_ms": p95_latency,
                "sample_count": count
            },
            "status_codes": dict(self.status_codes),
            "endpoint_hits": dict(self.endpoint_hits),
            "tool_executions": dict(self.tool_usage),
        }

    def get_prometheus_format(self) -> str:
        metrics = self.get_metrics()
        lines = [
            "# HELP resolvex_support_requests_total Total HTTP requests processed.",
            "# TYPE resolvex_support_requests_total counter",
            f"resolvex_support_requests_total {metrics['total_requests']}",
            "# HELP resolvex_support_errors_total Total HTTP error responses.",
            "# TYPE resolvex_support_errors_total counter",
            f"resolvex_support_errors_total {metrics['total_errors']}",
            "# HELP resolvex_support_uptime_seconds Total runtime in seconds.",
            "# TYPE resolvex_support_uptime_seconds gauge",
            f"resolvex_support_uptime_seconds {metrics['uptime_seconds']}",
            "# HELP resolvex_support_latency_avg_ms Average request latency in milliseconds.",
            "# TYPE resolvex_support_latency_avg_ms gauge",
            f"resolvex_support_latency_avg_ms {metrics['latency']['avg_ms']}",
            "# HELP resolvex_support_latency_p95_ms 95th percentile latency in milliseconds.",
            "# TYPE resolvex_support_latency_p95_ms gauge",
            f"resolvex_support_latency_p95_ms {metrics['latency']['p95_ms']}",
        ]
        for tool, cnt in metrics["tool_executions"].items():
            lines.append(f'resolvex_support_tool_calls_total{{tool="{tool}"}} {cnt}')
        return "\n".join(lines) + "\n"


metrics_service = MetricsCollector()
