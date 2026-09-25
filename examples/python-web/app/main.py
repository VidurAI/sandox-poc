"""Minimal FastAPI app of the shape Cowork emits by default. Exists so the
POC has a real Python app to build and deploy; not the point of the POC."""
import os
from fastapi import FastAPI

app = FastAPI(title="renewal-tracker")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/")
def index() -> dict:
    return {"app": "renewal-tracker", "db": bool(os.getenv("DATABASE_URL"))}
