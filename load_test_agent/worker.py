"""Runs one load stage: `concurrency` threads, each holding a persistent
HTTP connection, hammering `target_url` for `duration_s` seconds and
recording every request's latency and outcome.
"""

from __future__ import annotations

import http.client
import threading
import time
from urllib.parse import urlparse

from .metrics import RequestResult


def _worker_loop(host: str, port: int, path: str, stop_at: float, out: list[RequestResult], lock: threading.Lock) -> None:
    local_results: list[RequestResult] = []
    conn = http.client.HTTPConnection(host, port, timeout=1.0)
    try:
        while time.monotonic() < stop_at:
            start = time.monotonic()
            success = True
            try:
                conn.request("GET", path)
                response = conn.getresponse()
                response.read()
                success = 200 <= response.status < 300
            except Exception:
                success = False
                try:
                    conn.close()
                except Exception:
                    pass
                conn = http.client.HTTPConnection(host, port, timeout=1.0)
            elapsed_ms = (time.monotonic() - start) * 1000
            local_results.append(RequestResult(latency_ms=elapsed_ms, success=success))
    finally:
        conn.close()

    with lock:
        out.extend(local_results)


def warm_up(target_url: str, attempts: int = 3, timeout_s: float = 10.0) -> None:
    """Fires a few throwaway requests before the first timed stage.

    A freshly spawned process's very first outbound socket on Windows can
    carry one-off overhead (AV/firewall inspection of a new process, OS
    socket-subsystem init) that has nothing to do with the target's actual
    behavior. Left unwarmed, that overhead lands inside stage 1's measured
    window and can look like a multi-second "bottleneck" that isn't real.
    A generous timeout here is intentional: this is allowed to be slow,
    it just isn't allowed to be *counted*.
    """
    parsed = urlparse(target_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"

    for _ in range(attempts):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
            conn.request("GET", path)
            conn.getresponse().read()
            conn.close()
        except Exception:
            pass


def run_stage(target_url: str, concurrency: int, duration_s: float) -> list[RequestResult]:
    parsed = urlparse(target_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"

    results: list[RequestResult] = []
    lock = threading.Lock()
    stop_at = time.monotonic() + duration_s

    threads = [
        threading.Thread(target=_worker_loop, args=(host, port, path, stop_at, results, lock))
        for _ in range(concurrency)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results
