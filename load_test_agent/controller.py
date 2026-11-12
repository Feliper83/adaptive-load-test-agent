"""The scale-up/hold/scale-down decision -- a pure function, exhaustively
unit-testable, so the thing that actually decides "is this a bottleneck" can
be reviewed and changed with confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .metrics import WindowStats

Action = Literal["scale_up", "hold", "scale_down"]


@dataclass(frozen=True)
class Thresholds:
    max_error_rate: float = 0.05
    """Hard ceiling: any higher and this concurrency level is a bottleneck, not noise."""

    max_p95_latency_ms: float = 300.0
    """Hard ceiling on p95 latency."""

    degraded_p95_latency_ms: float = 150.0
    """Soft ceiling: above this but below the hard ceiling, hold instead of ramping further."""


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str


def decide(stats: WindowStats, thresholds: Thresholds = Thresholds()) -> Decision:
    if stats.error_rate > thresholds.max_error_rate:
        return Decision(
            "scale_down",
            f"error rate {stats.error_rate:.1%} exceeds {thresholds.max_error_rate:.1%} "
            f"at {stats.requests} requests/{stats.duration_s:.1f}s",
        )

    if stats.p95_latency_ms > thresholds.max_p95_latency_ms:
        return Decision(
            "scale_down",
            f"p95 latency {stats.p95_latency_ms:.0f}ms exceeds hard ceiling "
            f"{thresholds.max_p95_latency_ms:.0f}ms",
        )

    if stats.p95_latency_ms > thresholds.degraded_p95_latency_ms:
        return Decision(
            "hold",
            f"p95 latency {stats.p95_latency_ms:.0f}ms above comfort threshold "
            f"{thresholds.degraded_p95_latency_ms:.0f}ms -- holding before ramping further",
        )

    return Decision("scale_up", "within all health thresholds")
