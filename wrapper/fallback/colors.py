"""Deterministic color options — the fallback used to fill Croma products'
blank color field when the LLM enrichment is unavailable or misses an item."""


FALLBACK_COLORS = {
    "refrigerator": ["Shiny Steel", "Elegant Inox", "Ebony Black"],
    "television": ["Black"],
    "washing machine": ["White", "Silver"],
    "laptop": ["Silver", "Grey"],
    "audio": ["Black", "Blue"],
    "air conditioner": ["White"],
    "smartphone": ["Black", "Blue", "Silver"],
}


def fallback_colors(category: str) -> list[str]:
    return FALLBACK_COLORS.get(category, ["Black"])
