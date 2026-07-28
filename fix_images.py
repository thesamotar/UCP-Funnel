import json
from pathlib import Path
from db.seed import CATEGORY_IMAGES, CATALOGS

ROOT = Path("/Users/swagataroy/Developments/NODE/UCP-Funnel")

for table, path_str, id_field, cat_field in CATALOGS:
    if "bigbasket" in table or "croma" in table:
        continue # skip originals
    path = ROOT / path_str
    print(f"Processing {path}...")
    data = json.loads(path.read_text())
    updated = 0
    for p in data["products"]:
        cat = p.get(cat_field)
        if cat and cat in CATEGORY_IMAGES:
            p["imageUrl"] = CATEGORY_IMAGES[cat]
            updated += 1
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated {updated} products in {path}")
