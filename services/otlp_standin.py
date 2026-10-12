"""A stand-in for the Collector's OTLP/HTTP port (Chapter 3).

It plays one part at a time on a fixed port: a healthy receiver
that decodes and counts spans, a closed port that refuses
connections, or a hung receiver that accepts connections and never
answers. Exporters cannot tell it from a real Collector at the
HTTP level, which is all the outage experiment needs. Since
Chapter 6 it also keeps full span records and decodes log records,
for the correlation tests.
"""

import gzip
import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1 import (
    metrics_service_pb2,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import (
    AnyValue,
    KeyValue,
)

Value = str | int | float | bool


@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    span_id: str
    parent_id: str
    name: str
    service: str
    attributes: dict[str, Value]
    links: tuple[str, ...]  # "trace_id:span_id" of each link
    resource: dict[str, Value]


@dataclass(frozen=True)
class MetricPoint:
    name: str
    service: str
    attributes: dict[str, Value]
    value: float  # a sum's value, a histogram's count, else 0


@dataclass(frozen=True)
class LogRecord:
    trace_id: str
    span_id: str
    body: str
    service: str
    attributes: dict[str, Value]


def _value(v: AnyValue) -> Value:
    kind = v.WhichOneof("value")
    found: Value = getattr(v, kind) if kind else ""
    return (
        found
        if isinstance(found, (str, int, float, bool))
        else str(found)
    )


def _attrs(items: list[KeyValue]) -> dict[str, Value]:
    return {kv.key: _value(kv.value) for kv in items}


class StandIn:
    def __init__(self, port: int) -> None:
        self.port = port
        self.mode = "down"
        self._lock = threading.Lock()
        self._spans: list[tuple[int, int, str]] = []
        self._records: list[SpanRecord] = []
        self._logs: list[LogRecord] = []
        self._points: list[MetricPoint] = []
        self._http: ThreadingHTTPServer | None = None
        self._listener: socket.socket | None = None
        self._held: list[socket.socket] = []
        self._holder: threading.Thread | None = None

    def spans(self) -> list[tuple[int, int, str]]:
        """(start ns, arrival ns, name) of every span received."""
        with self._lock:
            return list(self._spans)

    def records(self) -> list[SpanRecord]:
        with self._lock:
            return list(self._records)

    def logs(self) -> list[LogRecord]:
        with self._lock:
            return list(self._logs)

    def points(self) -> list[MetricPoint]:
        with self._lock:
            return list(self._points)

    def up(self) -> None:
        self._stop()
        handler = _handler(self)
        self._http = ThreadingHTTPServer(
            ("127.0.0.1", self.port), handler
        )
        threading.Thread(
            target=self._http.serve_forever, daemon=True
        ).start()
        self.mode = "up"

    def down(self) -> None:
        self._stop()
        self.mode = "down"

    def hang(self) -> None:
        self._stop()
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind(("127.0.0.1", self.port))
        lsock.listen(16)
        lsock.settimeout(0.2)
        self._listener = lsock
        self._holder = threading.Thread(
            target=self._hold, args=(lsock,), daemon=True
        )
        self._holder.start()
        self.mode = "hung"

    def _hold(self, lsock: socket.socket) -> None:
        while self._listener is lsock:
            try:
                conn, _ = lsock.accept()
            except OSError:
                continue
            self._held.append(conn)  # read nothing, answer nothing

    def _stop(self) -> None:
        if self._http is not None:
            self._http.shutdown()
            self._http.server_close()
            self._http = None
        if self._listener is not None:
            lsock, self._listener = self._listener, None
            lsock.close()
            # The holder polls accept() every 0.2 s; the port is free
            # only once that thread has let go of the socket.
            if self._holder is not None:
                self._holder.join(timeout=2)
                self._holder = None
        for conn in self._held:
            conn.close()
        self._held.clear()

    def _record(self, body: bytes) -> None:
        request = ExportTraceServiceRequest.FromString(body)
        now = time.time_ns()
        with self._lock:
            for resource in request.resource_spans:
                about = _attrs(list(resource.resource.attributes))
                service = str(about.get("service.name", ""))
                for scope in resource.scope_spans:
                    for span in scope.spans:
                        start = span.start_time_unix_nano
                        self._spans.append((start, now, span.name))
                        links = tuple(
                            f"{k.trace_id.hex()}:{k.span_id.hex()}"
                            for k in span.links
                        )
                        self._records.append(
                            SpanRecord(
                                span.trace_id.hex(),
                                span.span_id.hex(),
                                span.parent_span_id.hex(),
                                span.name,
                                service,
                                _attrs(list(span.attributes)),
                                links,
                                about,
                            )
                        )

    def _record_metrics(self, body: bytes) -> None:
        message = metrics_service_pb2.ExportMetricsServiceRequest
        request = message.FromString(body)
        with self._lock:
            for resource in request.resource_metrics:
                about = _attrs(list(resource.resource.attributes))
                service = str(about.get("service.name", ""))
                for scope in resource.scope_metrics:
                    for m in scope.metrics:
                        kind = m.WhichOneof("data")
                        data = getattr(m, kind) if kind else None
                        for p in data.data_points if data else []:
                            value = float(
                                getattr(p, "as_double", 0)
                                or getattr(p, "as_int", 0)
                                or getattr(p, "count", 0)
                            )
                            self._points.append(
                                MetricPoint(
                                    m.name,
                                    service,
                                    _attrs(list(p.attributes)),
                                    value,
                                )
                            )

    def _record_logs(self, body: bytes) -> None:
        request = ExportLogsServiceRequest.FromString(body)
        with self._lock:
            for resource in request.resource_logs:
                service = str(
                    _attrs(list(resource.resource.attributes)).get(
                        "service.name", ""
                    )
                )
                for scope in resource.scope_logs:
                    for log in scope.log_records:
                        self._logs.append(
                            LogRecord(
                                log.trace_id.hex(),
                                log.span_id.hex(),
                                str(_value(log.body)),
                                service,
                                _attrs(list(log.attributes)),
                            )
                        )


def _handler(standin: StandIn) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(
                int(self.headers["Content-Length"])
            )
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            if self.path == "/v1/traces":
                standin._record(body)
            if self.path == "/v1/logs":
                standin._record_logs(body)
            if self.path == "/v1/metrics":
                standin._record_metrics(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler
