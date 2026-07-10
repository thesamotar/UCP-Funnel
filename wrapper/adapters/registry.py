"""Connector registry: load enabled connectors from Supabase at startup and
instantiate their adapter classes.

REGISTRY maps connector name -> RetailerAdapter instance. It is populated by
load_registry() (called from the wrapper's FastAPI lifespan) and read by the
pipeline and the cart/checkout routes.
"""
from importlib import import_module

from ..db import db
from .base import RetailerAdapter

REGISTRY: dict[str, RetailerAdapter] = {}


async def load_registry() -> dict[str, RetailerAdapter]:
    resp = await (await db()).table("connectors").select("*").eq("enabled", True).execute()
    rows = resp.data or []
    if not rows:
        raise RuntimeError("no enabled connectors in the database — run `python -m db.seed`")
    REGISTRY.clear()
    for row in rows:
        module_path, _, cls_name = row["adapter_path"].partition(":")
        cls = getattr(import_module(module_path), cls_name)
        if not issubclass(cls, RetailerAdapter):
            raise RuntimeError(f"{row['adapter_path']} is not a RetailerAdapter")
        REGISTRY[row["name"]] = cls(row)
    print(f"[registry] loaded {len(REGISTRY)} connectors: {', '.join(sorted(REGISTRY))}")
    return REGISTRY
