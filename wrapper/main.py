"""Tata Neu UCP node — the wrapper API between LLM shopping agents and
Tata retailer backends. Exposes UCP-shaped search / cart / checkout and
serves the demo frontend at /.

Routes are split by action under wrapper/routes/ (config, search, cart,
checkout), with shared in-memory state in wrapper/state.py; this module just
assembles them and mounts the frontend.
Run: uvicorn wrapper.main:app --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .adapters import load_registry
from .routes import cart, chat, checkout, config, search


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles sends no Cache-Control, so browsers cache heuristically and
    can serve a stale app.js/style.css against a fresh index.html after a
    redeploy. no-cache forces revalidation; unchanged files still 304."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # populate the connector registry from Supabase; fails loudly if the DB
    # is unreachable or unseeded — the node is useless without connectors
    await load_registry()
    yield


app = FastAPI(title="Tata Neu UCP Node", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(config.router)
app.include_router(chat.router)
app.include_router(search.router)
app.include_router(cart.router)
app.include_router(checkout.router)

# serve the demo frontend at / (mounted last so API routes win)
app.mount("/", NoCacheStaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True), name="frontend")
