"""A self-contained HTTP target with a configurable breaking point, so the
agent is demoable end-to-end with zero external services: below `capacity`
concurrent in-flight requests it behaves like a healthy service; above it,
latency grows and it starts shedding load with 503s -- exactly the signature
the controller is designed to detect.
"""

from __future__ import annotations

import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _SaturationState:
    def __init__(self, capacity: int, base_latency_ms: float):
        self.capacity = capacity
        self.base_latency_ms = base_latency_ms
        self._active = 0
        self._lock = threading.Lock()

    def enter(self) -> int:
        with self._lock:
            self._active += 1
            return self._active

    def exit(self) -> None:
        with self._lock:
            self._active -= 1


def _make_handler(state: _SaturationState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        # Required for persistent (keep-alive) connections with unambiguous
        # framing. Every response below sets Content-Length explicitly --
        # without both of these, a client reusing a connection can block
        # waiting for EOF that never arrives while the server waits for the
        # next request on the same socket.
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 - matches BaseHTTPRequestHandler signature
            pass  # silence default per-request stderr logging

        def do_GET(self) -> None:
            active = state.enter()
            try:
                latency_ms = state.base_latency_ms
                overload = active - state.capacity
                will_error = False
                if overload > 0:
                    latency_ms += overload * 12.0
                    error_probability = min(0.9, overload / (state.capacity * 2))
                    will_error = random.random() < error_probability

                time.sleep(latency_ms / 1000.0)

                if will_error:
                    body = b'{"status":"unavailable"}'
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    body = b'{"status":"ok"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            finally:
                state.exit()

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 512  # default of 5 would reject bursts of concurrent connects


def start_mock_target(capacity: int = 50, base_latency_ms: float = 12.0, port: int = 0) -> tuple[_Server, str]:
    """Starts the mock target on a background thread and returns (server, base_url)."""
    state = _SaturationState(capacity, base_latency_ms)
    server = _Server(("127.0.0.1", port), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/"
