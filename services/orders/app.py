"""Orders service HTTP surface: lookup and idempotent refunds."""

from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.orders.faults import Faults
from services.orders.store import OrderStore, RefundError
from wrenholt.telemetry.framework import FRAMEWORK_TELEMETRY_OFF


class RefundIn(BaseModel):
    order_id: str
    amount_minor: int


def create_app(
    store: OrderStore, faults: Faults | None = None
) -> FastAPI:
    inject = faults if faults is not None else Faults()
    app = FastAPI(title="orders", telemetry=FRAMEWORK_TELEMETRY_OFF)

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "orders": store.count()}

    @app.get("/orders/{order_id}")
    def get_order(order_id: str) -> dict[str, object]:
        inject.apply()
        order = store.get(order_id)
        if order is None:
            raise HTTPException(404, "unknown order")
        return asdict(order)

    @app.post("/refunds")
    def refund(
        body: RefundIn,
        key: str | None = Header(
            default=None, alias="Idempotency-Key"
        ),
    ) -> JSONResponse:
        inject.apply()
        if not key:
            raise HTTPException(
                400, "Idempotency-Key header required"
            )
        try:
            done = store.refund(key, body.order_id, body.amount_minor)
        except RefundError as exc:
            raise HTTPException(exc.status, exc.detail) from exc
        if not done.replayed:
            inject.after_commit()  # FS-07 (Chapter 9)
        return JSONResponse(
            asdict(done), status_code=200 if done.replayed else 201
        )

    return app
