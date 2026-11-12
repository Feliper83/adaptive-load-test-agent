"""Orchestrates the ramp: run a stage, decide, ramp further or stop.

Unlike a fixed load profile (e.g. "run 500 users for 5 minutes"), this agent
discovers the target's actual capacity by ramping until the controller sees
a real degradation signature (error rate or latency), then reports the last
fully-healthy stage as the validated stable capacity -- the same thing a
human watching a dashboard during a load test would do, automated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .controller import Decision, Thresholds, decide
from .metrics import WindowStats, summarize
from .worker import run_stage, warm_up


@dataclass(frozen=True)
class StageResult:
    concurrency: int
    stats: WindowStats
    decision: Decision


@dataclass(frozen=True)
class LoadTestReport:
    stages: list[StageResult]
    stable_concurrency: int
    stable_throughput_rps: float
    stable_p95_latency_ms: float
    bottleneck_reason: str | None


def run_adaptive_load_test(
    target_url: str,
    *,
    start_concurrency: int = 10,
    max_concurrency: int = 1000,
    ramp_factor: float = 2.5,
    stage_duration_s: float = 1.0,
    max_stages: int = 8,
    thresholds: Thresholds = Thresholds(),
    on_stage=None,
) -> LoadTestReport:
    warm_up(target_url)

    concurrency = start_concurrency
    stages: list[StageResult] = []
    last_healthy: StageResult | None = None

    for _ in range(max_stages):
        start = time.monotonic()
        results = run_stage(target_url, concurrency, stage_duration_s)
        duration = time.monotonic() - start

        stats = summarize(results, duration)
        decision = decide(stats, thresholds)
        stage = StageResult(concurrency=concurrency, stats=stats, decision=decision)
        stages.append(stage)
        if on_stage:
            on_stage(stage)

        if decision.action != "scale_up":
            # First sign of trouble: stop here. last_healthy (if any) is the
            # validated stable capacity; this stage is the bottleneck.
            break

        last_healthy = stage
        if concurrency >= max_concurrency:
            break
        concurrency = min(max_concurrency, max(concurrency + 1, int(concurrency * ramp_factor)))

    final = last_healthy or stages[0]
    bottleneck_reason = stages[-1].decision.reason if stages[-1].decision.action != "scale_up" else None

    return LoadTestReport(
        stages=stages,
        stable_concurrency=final.concurrency,
        stable_throughput_rps=final.stats.throughput_rps,
        stable_p95_latency_ms=final.stats.p95_latency_ms,
        bottleneck_reason=bottleneck_reason,
    )
