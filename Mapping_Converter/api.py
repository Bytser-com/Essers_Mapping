"""HTTP API for the Mapping Converter (FastAPI): creates the app and registers the routers.

Covers the flow from approving a reviewed proposal up to storing the mapping package
on the shared SFTP server, as well as AI review of Excel mapping proposals.

The endpoints live in routers/ (one file per resource):

    routers/approve.py   POST /approve              approve a reviewed proposal (story 185)
    routers/convert.py   POST /convert              Excel proposal -> JSON mapping package (story 54)
                         POST /convert-and-upload   ... and store it as MPackage.json
    routers/review.py    POST /review-excel         AI review of Excel proposal via SFTP

Run locally from the Mapping_Converter folder:
    uvicorn api:app --reload --port 8001
Interactive documentation: http://localhost:8001/docs

In Kubernetes the service listens on port 8000 and is only reachable through the
frontend, which proxies /api/converter/*.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from routers import approve, convert, review
from scripts.config import cors_origins, is_swagger_enabled

# Re-exported for backward compatibility and test patching:
from sftp_service import download_proposal_excel_from_sftp

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    swagger_on = is_swagger_enabled()
    application = FastAPI(
        title="Mapping Converter API",
        version="1.1.0",
        docs_url="/docs" if swagger_on else None,
        redoc_url=None,
        openapi_url="/openapi.json" if swagger_on else None,
    )

    # Only needed when a browser calls this API directly (local frontend development).
    _origins = cors_origins()
    if _origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    application.include_router(approve.router)
    application.include_router(convert.router)
    application.include_router(review.router)

    if swagger_on:
        @application.get("/swagger", include_in_schema=False)
        def swagger_redirect():
            return RedirectResponse(url="/docs")

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "mapping-converter"}

    return application


app = create_app()


__all__ = ["app", "download_proposal_excel_from_sftp"]
