"""Tata Neu UCP node — the wrapper API between LLM shopping agents and
Tata retailer backends. Exposes UCP-shaped search / cart / checkout and
serves the demo frontend at /.

Routes are split by action under wrapper/routes/ (config, search, cart,
checkout), with shared in-memory state in wrapper/state.py; this module just
assembles them and mounts the frontend.
Run: uvicorn wrapper.main:app --port 8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import cart, checkout, config, search

app = FastAPI(title="Tata Neu UCP Node")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(config.router)
app.include_router(search.router)
app.include_router(cart.router)
app.include_router(checkout.router)

# serve the demo frontend at / (mounted last so API routes win)
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True), name="frontend")
