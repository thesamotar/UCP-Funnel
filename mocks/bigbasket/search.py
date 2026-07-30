"""BigBasket product search + detail (RPC style: POST product.search)."""
from fastapi import APIRouter
from pydantic import BaseModel

from .store import DATA

router = APIRouter()


class SearchFilters(BaseModel):
    price_max: float | None = None
    price_min: float | None = None
    brand: str | None = None
    category: str | None = None


class SearchRequest(BaseModel):
    search_term: str
    filters: SearchFilters = SearchFilters()
    page_size: int = 10


def _matches(product: dict, req: SearchRequest) -> int:
    """Score a product against the search term; 0 = no match.

    Price is a hard constraint. Category and brand are LLM-guessed hints: a
    matching hint boosts ranking, but a wrong guess must never zero out a
    product the search term already matched. (Treating category as a hard
    filter made every grocery search except 'dairy' — the category primed as
    the routing example — come back empty.)"""
    f = req.filters
    if f.price_max is not None and product["sp"] > f.price_max:
        return 0
    if f.price_min is not None and product["sp"] < f.price_min:
        return 0

    desc = product["desc"].lower()
    haystack = f"{product['desc']} {product['brand']} {product['cat']}".lower()
    terms = [t for t in req.search_term.lower().split() if len(t) > 1]
    score = sum(2 if t in desc else 1 for t in terms if t in haystack)
    if score == 0:
        return 0
    if f.category and any(w in product["cat"].lower()
                          for w in f.category.lower().split() if len(w) > 1):
        score += 3
    if f.brand and f.brand.lower() in product["brand"].lower():
        score += 2
    return score


@router.post("/bb/api/v1/product.search")
def product_search(req: SearchRequest):
    scored = [(_matches(p, req), p) for p in DATA]
    hits = [p for s, p in sorted(scored, key=lambda x: -x[0]) if s > 0]
    return {
        "status": "success",
        "tab_info": {"search_term": req.search_term, "total_count": len(hits)},
        "products": hits[: req.page_size],
    }


@router.get("/bb/api/v1/product/{sku_id}")
def product_detail(sku_id: str):
    for p in DATA:
        if p["sku_id"] == sku_id:
            return {"status": "success", "product": p}
    return {"status": "error", "message": "SKU not found"}
