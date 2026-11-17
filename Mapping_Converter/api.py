"""Mapping Converter API placeholder service."""

from fastapi import FastAPI

app = FastAPI(title="Mapping Converter Placeholder", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "mapping-converter"}


@app.get("/")
def root():
    return {"message": "Mapping Converter Service (placeholder)"}
