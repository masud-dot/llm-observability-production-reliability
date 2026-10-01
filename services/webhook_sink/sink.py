"""Webhook sink for the alert smoke test (stdlib only).

POST /alert records a notification; GET /received reports the
count so the smoke script can poll it."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

RECEIVED: list[str] = []


class Sink(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size).decode("utf-8", "replace")
        RECEIVED.append(body)
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        payload = json.dumps({"count": len(RECEIVED)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8099), Sink).serve_forever()
