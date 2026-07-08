"""Deterministic retailer routing — the keyword-hint fallback used when the LLM
router is unavailable (no key) or returns something unusable."""


BIGBASKET_HINTS = {
    "milk", "bread", "egg", "eggs", "atta", "rice", "dal", "oil", "sugar", "salt",
    "tea", "coffee", "butter", "paneer", "curd", "biscuit", "snack", "chips",
    "banana", "onion", "tomato", "potato", "apple", "fruit", "vegetable",
    "grocery", "groceries", "detergent", "handwash", "dishwash", "noodles", "juice",
}
CROMA_HINTS = {
    "refrigerator", "fridge", "tv", "television", "laptop", "phone", "smartphone",
    "mobile", "washing", "machine", "ac", "conditioner", "headphone", "headphones",
    "earbuds", "speaker", "electronics", "appliance", "macbook", "samsung", "lg",
}


def fallback_route(query: str, constraints: dict) -> dict:
    """Pick a retailer by counting category keywords; mirrors the intent shape
    the LLM router would return."""
    words = query.lower().split()
    bb = sum(1 for w in words if w.strip(".,") in BIGBASKET_HINTS)
    cr = sum(1 for w in words if w.strip(".,") in CROMA_HINTS)
    return {
        "retailer": "bigbasket" if bb > cr else "croma",
        "search_term": query,
        "max_price": constraints.get("max_price"),
        "min_price": constraints.get("min_price"),
        "category": None,
        "brand": None,
        "min_capacity_litres": None,
        "reasoning": "keyword fallback (no LLM key configured)",
    }
