"""Command-line entrypoint.

    adaptive-load-test demo                         # self-contained, no setup needed
    adaptive-load-test run --target-url http://host/path

`demo` spins up the bundled mock target (configurable breaking point) and
runs the agent against it, so the whole mechanism is visible with one
command and no infrastructure.
"""

from __future__ import annotations

import argparse
import sys

from .agent import StageResult, run_adaptive_load_test
from .controller import Thresholds
from .mock_target import start_mock_target


def _print_stage(stage: StageResult) -> None:
    s = stage.stats
    print(
        f"[concurrency {stage.concurrency:>4}] requests={s.requests:<5} "
        f"error_rate={s.error_rate:.1%} p50={s.p50_latency_ms:.0f}ms p95={s.p95_latency_ms:.0f}ms "
        f"throughput={s.throughput_rps:.0f}req/s -> {stage.decision.action.upper()} ({stage.decision.reason})"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adaptive-load-test")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--start-concurrency", type=int, default=10)
    common.add_argument("--max-concurrency", type=int, default=1000)
    common.add_argument("--ramp-factor", type=float, default=2.5)
    common.add_argument("--stage-duration", type=float, default=1.0)
    common.add_argument("--max-stages", type=int, default=8)
    common.add_argument("--max-error-rate", type=float, default=0.05)
    common.add_argument("--max-p95-latency-ms", type=float, default=300.0)
    common.add_argument("--degraded-p95-latency-ms", type=float, default=150.0)

    demo = sub.add_parser("demo", parents=[common], help="Run against the bundled mock target")
    demo.set_defaults(max_concurrency=100)
    demo.add_argument("--capacity", type=int, default=30, help="Mock target's concurrent-request breaking point")
    demo.add_argument("--base-latency-ms", type=float, default=12.0)

    run = sub.add_parser("run", parents=[common], help="Run against a real target URL")
    run.add_argument("--target-url", required=True)

    return parser


def _run_common(target_url: str, args: argparse.Namespace) -> int:
    thresholds = Thresholds(
        max_error_rate=args.max_error_rate,
        max_p95_latency_ms=args.max_p95_latency_ms,
        degraded_p95_latency_ms=args.degraded_p95_latency_ms,
    )

    print(f"Starting adaptive load test against {target_url}\n")
    report = run_adaptive_load_test(
        target_url,
        start_concurrency=args.start_concurrency,
        max_concurrency=args.max_concurrency,
        ramp_factor=args.ramp_factor,
        stage_duration_s=args.stage_duration,
        max_stages=args.max_stages,
        thresholds=thresholds,
        on_stage=_print_stage,
    )

    print(f"\nValidated stable capacity: {report.stable_concurrency} concurrent users, "
          f"{report.stable_throughput_rps:.0f} req/s, p95 {report.stable_p95_latency_ms:.0f}ms")
    if report.bottleneck_reason:
        print(f"Bottleneck detected: {report.bottleneck_reason}")
        return 1
    print("No bottleneck found within --max-concurrency / --max-stages.")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    server, target_url = start_mock_target(capacity=args.capacity, base_latency_ms=args.base_latency_ms)
    print(f"Mock target started at {target_url} (breaking point: {args.capacity} concurrent requests)\n")
    try:
        return _run_common(target_url, args)
    finally:
        server.shutdown()


def cmd_run(args: argparse.Namespace) -> int:
    return _run_common(args.target_url, args)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        return cmd_demo(args)
    if args.command == "run":
        return cmd_run(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
