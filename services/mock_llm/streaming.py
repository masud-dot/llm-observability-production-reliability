"""Streaming for the mock provider (Chapter 8, SIMULATED).

Chapter 1's mock answers whole responses only. This wrapper takes
a request with "stream": true, asks the unchanged app for the whole
answer, and replays it as OpenAI-style server-sent events on a
fixed schedule. Faults live in the schedule: FS-02 delays the first
chunk; FS-04 ends the stream early, after HTTP 200. The wrapper
also notices when the client goes away, and stops sending. Chapter
11: asked for usage, it sends it in a last chunk without choices,
as OpenAI does, and only when the stream completes.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx2

Scope = dict[str, Any]
Event = dict[str, Any]


@dataclass(frozen=True)
class Schedule:
    first_s: float = 0.4  # before the first chunk
    gap_s: float = 0.12  # between chunks
    words: int = 1  # words per chunk
    cut_after: int | None = None  # end after this many chunks
    error_after: int | None = None  # an error event after this many
    faulty: int = 1_000_000  # how many requests get the fault


STEADY = Schedule()
# FS-02: the provider queues the request, then streams at its usual
# pace. Only the wait before the first chunk changes.
FS02_BROWNOUT = Schedule(first_s=3.0)
# FS-04: the stream ends after three chunks, after HTTP 200.
FS04_CUT = Schedule(cut_after=3)
SCHEDULES = {"fs02": FS02_BROWNOUT, "fs04": FS04_CUT}


@dataclass
class Sent:
    """What the provider sent for one streamed request."""

    planned: int
    chunks: int = 0
    outcome: str = "streaming"  # complete, cut, error, client_gone


def pieces(text: str, words: int) -> list[str]:
    split = text.split(" ")
    out = []
    for i in range(0, len(split), words):
        piece = " ".join(split[i : i + words])
        out.append(piece + (" " if i + words < len(split) else ""))
    return out


class Streaming:
    """An ASGI wrapper that streams chat completions."""

    def __init__(
        self,
        app: Any,
        schedule: Schedule = STEADY,
        log: list[Sent] | None = None,
    ) -> None:
        self.app, self.schedule = app, schedule
        self.log = log if log is not None else []
        self._requests = 0
        transport = httpx2.ASGITransport(app=app)
        self._inner = httpx2.AsyncClient(
            transport=transport, base_url="http://mock"
        )

    def use(self, schedule: Schedule) -> None:
        """Switch schedules between requests; faults count afresh."""
        self.schedule, self._requests = schedule, 0

    async def __call__(
        self, scope: Scope, receive: Any, send: Any
    ) -> None:
        path = scope.get("path")
        if scope["type"] != "http" or path != "/v1/chat/completions":
            await self.app(scope, receive, send)
            return
        body = await _read_body(receive)
        request = json.loads(body or b"{}")
        if not request.get("stream"):
            await self.app(scope, _replay(body), send)
            return
        request["stream"] = False
        options = request.pop("stream_options", None) or {}
        usage = bool(options.get("include_usage"))
        headers = {
            k.decode(): v.decode() for k, v in scope["headers"]
        }
        headers.pop("content-length", None)
        whole = await self._inner.post(
            "/v1/chat/completions", json=request, headers=headers
        )
        if whole.status_code != 200:  # errors arrive before streaming
            await _send_whole(send, whole)
            return
        await self._stream(whole.json(), receive, send, usage)

    async def _stream(
        self,
        answer: dict[str, Any],
        receive: Any,
        send: Any,
        usage: bool = False,
    ) -> None:
        plan = self.schedule
        fault = self._requests < plan.faulty
        self._requests += 1
        cut = plan.cut_after if fault else None
        fail = plan.error_after if fault else None
        text = answer["choices"][0]["message"]["content"]
        chunks = pieces(text, plan.words)
        sent = Sent(planned=len(chunks))
        self.log.append(sent)
        gone = asyncio.Event()
        watcher = asyncio.create_task(_watch(receive, gone))
        try:
            await send(_start())
            if await _wait(gone, plan.first_s):
                sent.outcome = "client_gone"
                return
            for i, piece in enumerate(chunks):
                if i == cut:  # after HTTP 200: no finish, no DONE
                    sent.outcome = "cut"
                    await send(_body(b"", more=False))
                    return
                if i == fail:
                    sent.outcome = "error"
                    await send(_body(_error_event(), more=False))
                    return
                delta = {"content": piece}
                if i == 0:
                    delta["role"] = "assistant"
                await send(_body(_chunk(answer, delta, None)))
                sent.chunks += 1
                if await _wait(gone, plan.gap_s):
                    sent.outcome = "client_gone"
                    return
            finish = answer["choices"][0]["finish_reason"]
            await send(_body(_chunk(answer, {}, finish)))
            if usage:
                await send(_body(_usage(answer)))
            await send(_body(b"data: [DONE]\n\n", more=False))
            sent.outcome = "complete"
        except OSError:  # the server found the client gone first
            sent.outcome = "client_gone"
        finally:
            watcher.cancel()


async def _watch(receive: Any, gone: asyncio.Event) -> None:
    while (await receive())["type"] != "http.disconnect":
        pass
    gone.set()


async def _wait(gone: asyncio.Event, seconds: float) -> bool:
    """Sleep, but wake early if the client goes away."""
    try:
        await asyncio.wait_for(gone.wait(), seconds)
    except TimeoutError:
        return False
    return True


def _start() -> Event:
    return {
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/event-stream")],
    }


def _body(data: bytes, more: bool = True) -> Event:
    return {
        "type": "http.response.body",
        "body": data,
        "more_body": more,
    }


def _chunk(
    answer: dict[str, Any], delta: dict[str, str], finish: str | None
) -> bytes:
    chunk = {
        "id": answer["id"],
        "object": "chat.completion.chunk",
        "created": answer["created"],
        "model": answer["model"],
        "choices": [
            {"index": 0, "delta": delta, "finish_reason": finish}
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n".encode()


def _usage(answer: dict[str, Any]) -> bytes:
    """The last chunk when usage is asked for: no choices."""
    chunk = {
        "id": answer["id"],
        "object": "chat.completion.chunk",
        "created": answer["created"],
        "model": answer["model"],
        "choices": [],
        "usage": answer["usage"],
    }
    return f"data: {json.dumps(chunk)}\n\n".encode()


def _error_event() -> bytes:
    error = {"message": "Overloaded.", "type": "overloaded_error"}
    data = json.dumps({"error": error})
    return f"event: error\ndata: {data}\n\n".encode()


async def _send_whole(send: Any, whole: httpx2.Response) -> None:
    headers = [
        (k.encode(), v.encode())
        for k, v in whole.headers.items()
        if k != "content-length"
    ]
    await send({
        "type": "http.response.start",
        "status": whole.status_code,
        "headers": headers,
    })  # fmt: skip
    await send(_body(whole.content, more=False))


async def _read_body(receive: Any) -> bytes:
    body = b""
    while True:
        message = await receive()
        part: bytes = message.get("body", b"")
        body += part
        if not message.get("more_body"):
            return body


def _replay(body: bytes) -> Any:
    sent = False

    async def receive() -> Event:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    return receive
