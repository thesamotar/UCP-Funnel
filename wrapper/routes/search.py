"""POST /ucp/v1/search — run the 4-stage search pipeline and cache the
returned items so later cart ops can resolve ids without re-querying."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..pipeline import run_search_pipeline
from ..state import CATALOG_CACHE

router = APIRouter()


class SearchBody(BaseModel):
    query: str
    constraints: dict = {}


@router.post("/ucp/v1/search")
async def ucp_search(body: SearchBody):
    try:
        result = await run_search_pipeline(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for item in result["items"]:
        CATALOG_CACHE[item["id"]] = item
    return result
