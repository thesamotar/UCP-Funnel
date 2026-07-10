"""Supabase Auth for the UCP endpoints.

The browser logs in with supabase-js and sends the session's access token as
`Authorization: Bearer <jwt>` on every node call. `current_user` verifies the
token locally (no network round-trip per request) and yields the user id that
carts/orders are keyed by.

Verification key: prefer the project's legacy HS256 secret (SUPABASE_JWT_SECRET)
when set; otherwise fetch the project's JWKS once and verify the asymmetric
signature (new Supabase projects sign with ES256/RS256 by default).
"""
import os
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True)


def _decode(token: str) -> dict:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if secret:
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    key = _jwks_client().get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")


async def current_user(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: returns the authenticated Supabase user id (uuid)."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="missing bearer token — sign in first")
    try:
        claims = _decode(token.strip())
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="token has no subject")
    return user_id
