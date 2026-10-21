"""Linnet's tools, and one execute_tool span per call (Chapter 9).

The model proposes a call; this module checks its arguments
against the tool's schema before anything runs, then runs it. A
span records the tool, the call ID, how the call ended and a keyed
fingerprint of its arguments, never the arguments or the result:
those are content, and only the facts built from a result reach
the model's answer.
"""

import hashlib
import json
import time
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wrenholt.gateway import ToolCall, ToolSpec
from wrenholt.privacy.pseudonym import Keys, pseudonym
from wrenholt.telemetry import conventions as c
from wrenholt.tools.errors import ToolError, ToolErrorType
from wrenholt.tools.orders import OrdersClient, RefundReceipt

LOOKUP, REFUND, FINISH = "lookup_order", "issue_refund", "finish"
ORDER = r"^WG-\d{6}$"


class LookupArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(pattern=ORDER)


class RefundArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(pattern=ORDER)
    amount_minor: int = Field(gt=0)


class FinishArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


SCHEMAS: dict[str, type[BaseModel]] = {
    LOOKUP: LookupArgs,
    REFUND: RefundArgs,
    FINISH: FinishArgs,
}
SPECS = (
    ToolSpec(
        LOOKUP,
        "Look up an order's status, date and total.",
        LookupArgs.model_json_schema(),
    ),
    ToolSpec(
        REFUND,
        "Refund part or all of a delivered order, in pence.",
        RefundArgs.model_json_schema(),
    ),
    ToolSpec(
        FINISH,
        "Call when you have what you need to answer.",
        FinishArgs.model_json_schema(),
    ),
)


@dataclass(frozen=True)
class ToolResult:
    content: str  # JSON for the model: content, never exported
    fact: str = ""  # what the answer may use


def canonical(arguments: str) -> str:
    """The same arguments, however the model spaced or ordered
    them; text that is not JSON stays as it is."""
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return arguments
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def parse(call: ToolCall) -> BaseModel:
    schema = SCHEMAS.get(call.name)
    if schema is None:
        raise ToolError(ToolErrorType.INVALID_ARGUMENTS, call.name)
    try:
        return schema.model_validate_json(call.arguments)
    except ValidationError as exc:
        kind = ToolErrorType.INVALID_ARGUMENTS
        raise ToolError(kind, call.name) from exc


def refund_key(invocation: str, args: RefundArgs) -> str:
    """One key per logical refund: this invocation, this order,
    this amount. Every retry of it sends the same key."""
    raw = f"{invocation}|{args.order_id}|{args.amount_minor}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def pounds(minor: int) -> str:
    return f"£{minor // 100}.{minor % 100:02d}"


class Toolbox:
    def __init__(
        self,
        agent: str,
        keys: Keys,
        *,
        tracer_provider: trace.TracerProvider | None = None,
        meter_provider: metrics.MeterProvider | None = None,
    ) -> None:
        self._agent, self._keys = agent, keys
        self._tracer = trace.get_tracer(
            "wrenholt.tools", tracer_provider=tracer_provider
        )
        meter = metrics.get_meter(
            "wrenholt.tools", meter_provider=meter_provider
        )
        self._duration = meter.create_histogram(
            c.TOOL_DURATION,
            unit="s",
            description="Tool execution duration.",
            explicit_bucket_boundaries_advisory=c.DURATION_BUCKETS,
        )

    async def run(
        self, call: ToolCall, invocation: str, orders: OrdersClient
    ) -> ToolResult:
        measured = {
            c.TOOL_NAME: call.name,
            c.TOOL_TYPE: "function",
            c.AGENT_NAME: self._agent,
        }
        attrs = {  # set at creation: sampling may read them
            c.OPERATION_NAME: c.EXECUTE_TOOL,
            **measured,
            c.TOOL_CALL_ID: call.id,
            c.TOOL_FINGERPRINT: pseudonym(
                "args", canonical(call.arguments), self._keys
            ),
        }
        start = time.perf_counter()
        with self._tracer.start_as_current_span(
            f"{c.EXECUTE_TOOL} {call.name}",
            kind=SpanKind.INTERNAL,
            attributes=attrs,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                result = await self._dispatch(
                    parse(call), invocation, orders, span
                )
            except ToolError as err:
                kind = err.error_type.value
                span.set_attribute(c.ERROR_TYPE, kind)
                span.set_status(Status(StatusCode.ERROR))
                measured[c.ERROR_TYPE] = kind
                result = failed(call.name, err)
        self._duration.record(time.perf_counter() - start, measured)
        return result

    async def _dispatch(
        self,
        args: BaseModel,
        invocation: str,
        orders: OrdersClient,
        span: Span,
    ) -> ToolResult:
        if isinstance(args, LookupArgs):
            return await lookup(orders, args)
        if isinstance(args, RefundArgs):
            return await self._refund(orders, args, invocation, span)
        raise ToolError(ToolErrorType.INVALID_ARGUMENTS, "finish")

    async def _refund(
        self,
        orders: OrdersClient,
        args: RefundArgs,
        invocation: str,
        span: Span,
    ) -> ToolResult:
        key = refund_key(invocation, args)  # once, outside any retry
        try:
            done = await orders.refund(
                args.order_id, args.amount_minor, key
            )
        except ToolError as err:
            if err.error_type is not ToolErrorType.TIMEOUT:
                raise
            # A timeout says nothing about whether the refund was
            # made. With the same key, asking again is safe: the
            # service answers with the refund it already made.
            done = await orders.refund(
                args.order_id, args.amount_minor, key
            )
        span.set_attribute(c.TOOL_REPLAYED, done.replayed)
        return refunded(done)


def refunded(done: RefundReceipt) -> ToolResult:
    content = {
        "refund_id": done.refund_id,
        "amount_minor": done.amount_minor,
    }
    fact = (
        f"Refund {done.refund_id}: {pounds(done.amount_minor)} "
        "to the original payment method."
    )
    return ToolResult(json.dumps(content), fact)


async def lookup(
    orders: OrdersClient, args: LookupArgs
) -> ToolResult:
    facts = await orders.lookup(args.order_id)
    if facts is None:
        missing = f"No order {args.order_id} exists."
        return ToolResult(json.dumps({"found": False}), missing)
    data = {
        "found": True,
        "status": facts.status,
        "placed_on": facts.placed_on,
        "total_minor": facts.total_minor,
    }
    fact = (
        f"Order {facts.order_id}: {facts.status}, placed on "
        f"{facts.placed_on}, total {pounds(facts.total_minor)}."
    )
    return ToolResult(json.dumps(data), fact)


def failed(name: str, err: ToolError) -> ToolResult:
    """What the model is told when a call fails, and the fact the
    answer may use."""
    content = json.dumps({"error": err.error_type.value})
    if name != REFUND:
        return ToolResult(content)
    if err.error_type is ToolErrorType.REJECTED:
        return ToolResult(content, f"Refund refused: {err.detail}.")
    return ToolResult(content, "Refund not confirmed: no answer.")
