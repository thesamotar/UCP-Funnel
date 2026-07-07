"""Mock BigBasket API — grocery retailer backend.

Deliberately uses BigBasket-ish conventions: POST search, snake_case,
`sp`/`mrp` pricing, availability flags "A"/"O".
Run: uvicorn mocks.bigbasket_api:app --port 9001
"""
import json
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock BigBasket API")

DATA = json.loads((Path(__file__).parent / "bigbasket_data.json").read_text())["products"]


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
    """Score a product against the search term; 0 = no match."""
    terms = [t for t in req.search_term.lower().split() if len(t) > 1]
    haystack = f"{product['desc']} {product['brand']} {product['cat']}".lower()
    score = sum(2 if t in product["desc"].lower() else 1 for t in terms if t in haystack)
    f = req.filters
    if f.price_max is not None and product["sp"] > f.price_max:
        return 0
    if f.price_min is not None and product["sp"] < f.price_min:
        return 0
    if f.brand and f.brand.lower() not in product["brand"].lower():
        return 0
    if f.category and f.category.lower() not in product["cat"].lower():
        return 0
    return score


@app.post("/bb/api/v1/product.search")
def product_search(req: SearchRequest):
    scored = [(_matches(p, req), p) for p in DATA]
    hits = [p for s, p in sorted(scored, key=lambda x: -x[0]) if s > 0]
    return {
        "status": "success",
        "tab_info": {"search_term": req.search_term, "total_count": len(hits)},
        "products": hits[: req.page_size],
    }


@app.get("/bb/api/v1/product/{sku_id}")
def product_detail(sku_id: str):
    for p in DATA:
        if p["sku_id"] == sku_id:
            return {"status": "success", "product": p}
    return {"status": "error", "message": "SKU not found"}
