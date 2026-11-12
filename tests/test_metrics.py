import pytest

from load_test_agent.metrics import RequestResult, summarize


def test_summarize_computes_error_rate_and_throughput() -> None:
    results = [
        RequestResult(latency_ms=10, success=True),
        RequestResult(latency_ms=20, success=True),
        RequestResult(latency_ms=30, success=False),
        RequestResult(latency_ms=40, success=True),
    ]

    stats = summarize(results, duration_s=2.0)

    assert stats.requests == 4
    assert stats.successes == 3
    assert stats.failures == 1
    assert stats.error_rate == 0.25
    assert stats.throughput_rps == 2.0


def test_summarize_percentiles_on_sorted_values() -> None:
    results = [RequestResult(latency_ms=v, success=True) for v in [10, 20, 30, 40, 100]]

    stats = summarize(results, duration_s=1.0)

    assert stats.p50_latency_ms == 30
    assert stats.p95_latency_ms == pytest.approx(88.0)


def test_summarize_empty_results_does_not_divide_by_zero() -> None:
    stats = summarize([], duration_s=1.0)

    assert stats.requests == 0
    assert stats.error_rate == 0.0
    assert stats.throughput_rps == 0.0
    assert stats.p95_latency_ms == 0.0
