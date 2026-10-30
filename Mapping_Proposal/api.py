"""HTTP API for the mapping tool (FastAPI): creates the app and registers the routers.

The endpoints themselves live in routers/ (one file per resource). Like main.py,
the routes stay thin and call the ``scripts`` package.

Run locally from the Mapping_Proposal folder:
    uvicorn api:app --reload --port 8000
Interactive documentation: http://localhost:8000/docs

In Kubernetes the service listens on port 8000 and is only reachable through the
frontend, which proxies /api/proposal/*.

While the API runs, the incoming watcher starts the AI automatically for every complete
upload in INCOMING_DIR (see services/incoming_watcher.py). WATCH_INCOMING=0 turns it off.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import proposals
from services import incoming_watcher
from scripts.config import cors_origins, watch_incoming_enabled


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start watching for uploads together with the API, stop it when the API stops.
    stop = None
    if watch_incoming_enabled():
        _, stop = incoming_watcher.start_in_background()
    yield
    if stop is not None:
        stop.set()


app = FastAPI(title='Mapping Proposal API', version='0.1.0', lifespan=lifespan)

# Only needed when a browser calls this API directly (local frontend development).
_origins = cors_origins()
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=['GET'], allow_headers=['*'])

app.include_router(proposals.router)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}
