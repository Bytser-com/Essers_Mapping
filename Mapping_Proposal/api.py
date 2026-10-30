"""FastAPI HTTP API for the Mapping Proposal service."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import customers, upload

app = FastAPI(
    title='AI Mapping Engine API',
    description='API for uploading XML interfaces, generating proposals, and managing customer SFTP storage',
    version='0.1.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(upload.router)
app.include_router(customers.router)


@app.get('/healthz')
async def healthz():
    return {'status': 'healthy'}
