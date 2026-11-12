"""Turns raw per-request results into the window statistics the controller
decides on: error rate, p50/p95 latency, throughput.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestResult:
    latency_ms: float
    success: bool


@dataclass(frozen=True)
class WindowStats:
    requests: int
    successes: int
    failures: int
    duration_s: float
    p50_latency_ms: float
    p95_latency_ms: float

    @property
    def error_rate(self) -> float:
        return self.failures / self.requests if self.requests else 0.0

    @property
    def throughput_rps(self) -> float:
        return self.requests / self.duration_s if self.duration_s > 0 else 0.0


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    lower, upper = math.floor(k), math.ceil(k)
    if lower == upper:
        return sorted_values[int(k)]
    return sorted_values[lower] * (upper - k) + sorted_values[upper] * (k - lower)


def summarize(results: list[RequestResult], duration_s: float) -> WindowStats:
    requests = len(results)
    failures = sum(1 for r in results if not r.success)
    latencies = sorted(r.latency_ms for r in results)
    return WindowStats(
        requests=requests,
        successes=requests - failures,
        failures=failures,
        duration_s=duration_s,
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
    )
