# adaptive-load-test-agent

A load-testing agent that ramps concurrency adaptively based on live latency/error signatures, instead of running a
fixed load profile ("500 users for 5 minutes") and hoping that number meant something. It stops the moment the
target shows real degradation and reports the last fully-healthy concurrency level as the validated stable capacity.

## Why this exists

Built around a recurring stress-testing pattern: instead of guessing a load level up front, ramp until the system
actually tells you where its limit is. The controller watches error rate and p95 latency (hard ceiling + a softer
"comfort" ceiling) after every stage and decides `scale_up` / `hold` / `scale_down` -- the same reasoning a human
watching a Grafana dashboard during a load test would apply, automated and logged.

## How it works

1. A worker pool opens `concurrency` persistent HTTP connections and hammers the target for `stage_duration` seconds.
2. Results are summarized into error rate, p50/p95 latency, and throughput.
3. The controller (`controller.py`, a pure function) decides:
   - `scale_down` if error rate or p95 latency breaches a hard ceiling
   - `hold` if p95 latency is past a softer "comfort" threshold but not yet critical
   - `scale_up` otherwise
4. On `scale_up`, concurrency increases by `ramp_factor` and another stage runs. On `hold`/`scale_down`, the ramp
   stops immediately -- the previous `scale_up` stage is reported as the validated stable capacity.

## Try it (zero setup)

```bash
pip install -e ".[dev]"
adaptive-load-test demo
```

`demo` starts a bundled mock HTTP target with a configurable breaking point (`--capacity`, default 30 concurrent
in-flight requests) and runs the agent against it -- no external service needed. Above capacity, the mock target's
latency grows and it starts shedding load with 503s, which is exactly the signature the controller is built to catch.

Point it at a real service instead:

```bash
adaptive-load-test run --target-url http://localhost:8080/health
```

## A note on the demo's numbers

The bundled mock target and its client are both plain synchronous Python (stdlib `http.server` /`http.client`,
real OS threads, real sockets -- no aiohttp/asyncio) so the whole thing runs with zero dependencies. That also means
the demo's own thread scheduling becomes part of what you're measuring once concurrency climbs into the hundreds:
you may see the agent report a lower stable capacity on a busy or virtualized machine than on a quiet one. For
*validating the decision logic itself* that's irrelevant (and exhaustively unit-tested against synthetic
`WindowStats` in `test_controller.py`, independent of real threads/sockets). For a more statistically stable demo
reading, increase `--stage-duration` (more samples per stage smooths out scheduling noise). For real-world load
testing of a production service over a network, swap `worker.py`'s transport for an async client (aiohttp) or point
the controller at a dedicated tool's (k6, Locust) live metrics instead -- the ramp/decide/stop logic is the part
meant to be reused.

One more thing worth knowing if you reuse `worker.py`: the first request a freshly-started process makes can carry
one-off OS/AV socket-inspection overhead unrelated to the target's real behavior. `agent.py` fires a few throwaway
`warm_up()` requests before the first timed stage specifically so that cost doesn't get misread as a bottleneck.

## Project layout

```
load_test_agent/
  metrics.py       RequestResult -> WindowStats (error rate, p50/p95 latency, throughput)
  controller.py    pure scale_up/hold/scale_down decision + Thresholds
  mock_target.py   self-contained HTTP target with a configurable breaking point
  worker.py        thread-pool request generator + pre-stage warm-up
  agent.py         orchestrates the ramp, stops on first non-scale_up decision
  cli.py           argparse entrypoint (`demo` / `run` subcommands)
tests/
  test_metrics.py              percentile/error-rate/throughput math
  test_controller.py           exhaustive threshold-boundary tests
  test_agent_integration.py    real agent against the real mock server, both outcomes
```

## Run the tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
