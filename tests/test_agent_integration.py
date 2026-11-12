"""Integration test: runs the real agent (real threads, real sockets) against
the real mock target server -- nothing mocked out here except the "service
under test" itself, which is the point of mock_target.py.
"""

from load_test_agent.agent import run_adaptive_load_test
from load_test_agent.controller import Thresholds
from load_test_agent.mock_target import start_mock_target


def test_agent_detects_bottleneck_and_reports_stable_capacity_below_breaking_point() -> None:
    server, target_url = start_mock_target(capacity=20, base_latency_ms=5.0)
    try:
        report = run_adaptive_load_test(
            target_url,
            start_concurrency=5,
            ramp_factor=3.0,
            stage_duration_s=0.3,
            max_stages=6,
            thresholds=Thresholds(),
        )
    finally:
        server.shutdown()

    # Ramped through at least one healthy stage before hitting trouble.
    assert len(report.stages) >= 2
    assert report.stages[0].decision.action == "scale_up"

    # A bottleneck must have been found well inside max_stages, with the
    # breaking point exceeded by whichever stage triggered it.
    assert report.bottleneck_reason is not None
    assert report.stages[-1].decision.action != "scale_up"

    # The reported stable capacity must be a concurrency level that was
    # actually tested and found healthy -- not the stage that broke.
    healthy_concurrencies = [s.concurrency for s in report.stages if s.decision.action == "scale_up"]
    assert report.stable_concurrency in healthy_concurrencies
    assert report.stable_concurrency < report.stages[-1].concurrency


def test_agent_reports_no_bottleneck_when_ceiling_never_reached() -> None:
    # Capacity far above anything the agent will ramp to in 2 small stages.
    server, target_url = start_mock_target(capacity=10_000, base_latency_ms=1.0)
    try:
        report = run_adaptive_load_test(
            target_url,
            start_concurrency=5,
            ramp_factor=2.0,
            stage_duration_s=0.2,
            max_stages=2,
            max_concurrency=10,
        )
    finally:
        server.shutdown()

    assert report.bottleneck_reason is None
    assert all(s.decision.action == "scale_up" for s in report.stages)
