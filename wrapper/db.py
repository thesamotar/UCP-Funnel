"""Shared async Supabase client (service-role key, bypasses RLS).

Used by the wrapper for per-user carts/orders, the catalog cache, and the
connector registry — and by the mock retailers for their catalogs and native
state. No fallbacks: if Supabase is unreachable or the env vars are missing,
calls raise and surface as 5xx.
"""
import os

from supabase import AsyncClient, acreate_client

_client: AsyncClient | None = None


async def db() -> AsyncClient:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set (see .env)")
        _client = await acreate_client(url, key)
    return _client
