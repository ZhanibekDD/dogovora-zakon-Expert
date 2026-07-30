from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.signing import router as signing_router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="ZakonExpert Signing Service", docs_url=None, redoc_url=None)
app.include_router(signing_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
