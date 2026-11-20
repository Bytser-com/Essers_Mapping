"""HTTP API for the Mapping Converter (FastAPI): creates the app and registers the routers.

Covers the flow from approving a reviewed proposal up to storing the mapping package
on the shared SFTP server. The endpoints live in routers/ (one file per resource):

    routers/approve.py   POST /approve              approve a reviewed proposal (story 185)
    routers/review.py    POST /review-excel         AI consistency review of a proposal (story 51)
    routers/convert.py   POST /convert              Excel proposal -> JSON mapping package (story 54)
                         POST /convert-and-upload   ... and store it as MPackage.json

Run locally from the Mapping_Converter folder:
    uvicorn api:app --reload --port 8001
Interactive documentation: http://localhost:8001/docs

In Kubernetes the service listens on port 8000 and is only reachable through the
frontend, which proxies /api/converter/*.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import approve, convert, review
from scripts.config import cors_origins

logging.basicConfig(level=logging.INFO)

app = FastAPI(title='Mapping Converter API', version='1.0.0')

# Only needed when a browser calls this API directly (local frontend development).
_origins = cors_origins()
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=['GET', 'POST'], allow_headers=['*'])

app.include_router(approve.router)
app.include_router(review.router)
app.include_router(convert.router)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok', 'service': 'mapping-converter'}


@app.get('/')
def root() -> dict:
    return {'message': 'Mapping Converter Service'}
