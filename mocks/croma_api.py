"""Mock Croma API — electronics retailer backend.

Deliberately uses Croma-ish conventions: GET search with query params,
camelCase, nested price object, nested searchResult envelope.
Some products have specs.color = null on purpose — the wrapper's
enhance stage fills those gaps.
Run: uvicorn mocks.croma_api:app --port 9002
"""
import json
import re
from pathlib import Path

from fastapi import FastAPI

app = FastAPI(title="Mock Croma API")

DATA = json.loads((Path(__file__).parent / "croma_data.json").read_text())["products"]

CAPACITY_RE = re.compile(r"([\d.]+)\s*(l|kg|ton)", re.I)


def _capacity_litres(product: dict) -> float | None:
    cap = (product.get("specs") or {}).get("capacity") or ""
    m = CAPACITY_RE.match(cap.strip())
    return float(m.group(1)) if m and m.group(2).lower() == "l" else None


@app.get("/croma/api/v2/products/search")
def search(
    text: str,
    maxPrice: float | None = None,
    minPrice: float | None = None,
    category: str | None = None,
    minCapacityLitres: float | None = None,
    pageSize: int = 10,
):
    terms = [t for t in text.lower().split() if len(t) > 1]
    hits = []
    for p in DATA:
        haystack = f"{p['name']} {p['brandName']} {p['category']}".lower()
        score = sum(2 if t in p["name"].lower() else 1 for t in terms if t in haystack)
        if category and category.lower() in p["category"].lower():
            score += 3
        elif category and score == 0:
            continue
        if score == 0:
            continue
        price = p["price"]["sellingPrice"]
        if maxPrice is not None and price > maxPrice:
            continue
        if minPrice is not None and price < minPrice:
            continue
        if minCapacityLitres is not None:
            litres = _capacity_litres(p)
            if litres is None or litres < minCapacityLitres:
                continue
        hits.append((score, p))
    hits.sort(key=lambda x: -x[0])
    products = [p for _, p in hits[:pageSize]]
    return {"searchResult": {"products": products, "totalCount": len(products)}, "status": 200}


@app.get("/croma/api/v2/products/{code}")
def detail(code: str):
    for p in DATA:
        if p["code"] == code:
            return {"product": p, "status": 200}
    return {"product": None, "status": 404, "message": "not found"}
