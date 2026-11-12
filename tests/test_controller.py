from load_test_agent.controller import Thresholds, decide
from load_test_agent.metrics import WindowStats


def _stats(**overrides) -> WindowStats:
    base = dict(requests=100, successes=100, failures=0, duration_s=1.0, p50_latency_ms=20, p95_latency_ms=40)
    base.update(overrides)
    return WindowStats(**base)


def test_scales_up_when_healthy() -> None:
    assert decide(_stats()).action == "scale_up"


def test_scales_down_on_error_rate_ceiling() -> None:
    decision = decide(_stats(failures=10, successes=90))
    assert decision.action == "scale_down"
    assert "error rate" in decision.reason


def test_scales_down_on_hard_latency_ceiling() -> None:
    decision = decide(_stats(p95_latency_ms=400))
    assert decision.action == "scale_down"
    assert "hard ceiling" in decision.reason


def test_holds_on_soft_latency_ceiling() -> None:
    decision = decide(_stats(p95_latency_ms=200))
    assert decision.action == "hold"


def test_error_rate_checked_before_latency() -> None:
    # Both thresholds breached -- error rate should win since it's checked first
    # (it's the stronger signal: a service already shedding load, not just slow).
    decision = decide(_stats(failures=10, successes=90, p95_latency_ms=500))
    assert "error rate" in decision.reason


def test_custom_thresholds_are_respected() -> None:
    tight = Thresholds(max_error_rate=0.01, max_p95_latency_ms=50, degraded_p95_latency_ms=25)
    assert decide(_stats(p95_latency_ms=30), tight).action == "hold"
    assert decide(_stats(p95_latency_ms=60), tight).action == "scale_down"
