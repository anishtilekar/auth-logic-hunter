"""A tiny real HTTP server for replay tests.

Deliberately a real socket server, not a mocked transport: the race half of
Stage 6 is about genuine concurrent timing, and a mock that returns instantly
would make any implementation look correct. `atomic` switches the coupon redeem
between the planted check-then-act bug and a properly locked version, and
`enforce_ownership` does the same for the order endpoints — so the same replay
code can be shown to report confirmed *and* refuted against a live server.
"""

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class State:
    def __init__(self, *, atomic: bool, enforce_ownership: bool) -> None:
        self.atomic = atomic
        self.enforce_ownership = enforce_ownership
        self.lock = threading.Lock()
        self.coupons: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.counter = 0

    def next_id(self, prefix: str) -> str:
        with self.lock:
            self.counter += 1
            return f"{prefix}{self.counter}"


def _make_handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:  # keep test output clean
            pass

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @property
        def user(self) -> str:
            return self.headers.get("X-User", "")

        def do_OPTIONS(self) -> None:  # connection warm-up
            self._send(200, {})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            parts = self.path.strip("/").split("/")

            if self.path == "/api/coupons":
                code = state.next_id("C")
                state.coupons[code] = {"code": code, "owner": self.user, "redemptions": 0}
                self._send(201, {"code": code})
                return

            if len(parts) == 4 and parts[1] == "coupons" and parts[3] == "redeem":
                coupon = state.coupons.get(parts[2])
                if coupon is None:
                    self._send(404, {"error": "unknown coupon"})
                    return
                if state.atomic:
                    with state.lock:
                        if coupon["redemptions"] >= 1:
                            self._send(409, {"error": "already redeemed"})
                            return
                        coupon["redemptions"] += 1
                    self._send(200, {"code": coupon["code"], "redeemedBy": self.user})
                    return
                # Planted bug: check and act are separate, with a window between.
                if coupon["redemptions"] >= 1:
                    self._send(409, {"error": "already redeemed"})
                    return
                time.sleep(0.05)
                coupon["redemptions"] += 1
                self._send(200, {"code": coupon["code"], "redeemedBy": self.user})
                return

            if self.path == "/api/orders":
                oid = state.next_id("O")
                state.orders[oid] = {"order_id": oid, "owner": self.user}
                self._send(201, {"order_id": oid})
                return

            self._send(404, {"error": "no route"})

        def do_GET(self) -> None:
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[1] == "orders":
                order = state.orders.get(parts[2])
                if order is None:
                    self._send(404, {"error": "unknown order"})
                    return
                if state.enforce_ownership and order["owner"] != self.user:
                    self._send(403, {"error": "not your order"})
                    return
                self._send(200, order)
                return
            if len(parts) == 3 and parts[1] == "coupons":
                coupon = state.coupons.get(parts[2])
                self._send(200, coupon) if coupon else self._send(404, {"error": "unknown"})
                return
            self._send(404, {"error": "no route"})

    return Handler


def serve(*, atomic: bool = False, enforce_ownership: bool = False) -> Iterator[str]:
    state = State(atomic=atomic, enforce_ownership=enforce_ownership)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
