"""POST /ucp/v1/search — run the 4-stage search pipeline and cache the
returned items so later cart ops can resolve ids without re-querying.

Guardrail: the whole pipeline runs under one deadline (SEARCH_DEADLINE_S,
default 100s — enough for an LLM web-search enhance pass, never infinite).
"""
import asyncio
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..pipeline import PipelineError, run_search_pipeline
from ..state import CATALOG_CACHE

SEARCH_DEADLINE_S = float(os.environ.get("SEARCH_DEADLINE_S", "100"))

router = APIRouter()


class SearchBody(BaseModel):
    query: str
    constraints: dict = {}


@router.post("/ucp/v1/search")
async def ucp_search(body: SearchBody):
    try:
        result = await asyncio.wait_for(run_search_pipeline(body.model_dump()), SEARCH_DEADLINE_S)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except PipelineError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"search exceeded the {SEARCH_DEADLINE_S:.0f}s deadline and was aborted",
        )
    for item in result["items"]:
        CATALOG_CACHE[item["id"]] = item
    return result
