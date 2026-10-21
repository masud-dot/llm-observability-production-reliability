"""The incident service (Chapter 19).

    uvicorn wrenholt.api.incidents:app --port 8300

POST /alerts takes Grafana's webhook notifications; GET /incidents
lists the records; GET /incidents/{id}/postmortem drafts one from its
record. Records are kept in WRENHOLT_INCIDENTS, a JSON file.
"""

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import PlainTextResponse

from wrenholt.incidents import Incidents, postmortem


def create_app(store: Incidents | None = None) -> FastAPI:
    path = Path(
        os.environ.get("WRENHOLT_INCIDENTS", "incidents.json")
    )
    incidents = store if store is not None else Incidents(path)
    app = FastAPI(title="wrenholt-incidents")

    @app.post("/alerts", status_code=204)
    async def alerts(body: dict[str, Any]) -> Response:
        incidents.notify(body)
        return Response(status_code=204)

    @app.get("/incidents")
    async def listed() -> list[dict[str, Any]]:
        return [asdict(i) for i in incidents.all.values()]

    @app.get("/incidents/{incident_id}/postmortem")
    async def draft(incident_id: str) -> PlainTextResponse:
        found = incidents.all.get(incident_id)
        if found is None:
            raise HTTPException(404, "no such incident")
        return PlainTextResponse(postmortem(found))

    return app


app = create_app()
