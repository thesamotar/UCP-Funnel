"""Seed the Supabase database from the mock retailers' data.json files.

Run once after applying db/schema.sql:

    .venv/bin/python -m db.seed

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment
(run.sh sources .env; or `set -a; source .env` first).

Idempotent: upserts by primary key, safe to re-run after editing data.json
or the image map below. See db/data_sourcing_mock.md for how to add/replace
catalog data and product images.
"""
import json
import os
import sys
from pathlib import Path

from supabase import create_client

ROOT = Path(__file__).parent.parent

# One representative image per category, hotlinked from Wikimedia Commons
# (each URL verified to return an image). Categories without a good match
# are omitted — the frontend falls back to the category emoji.
CATEGORY_IMAGES = {
    # bigbasket
    "eggs": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Egg_cartons_with_chicken_eggs_03.jpg/500px-Egg_cartons_with_chicken_eggs_03.jpg",
    "beverages": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2d/Black_coffee_with_saucer_and_spoon.jpg/500px-Black_coffee_with_saucer_and_spoon.jpg",
    "snacks": "https://upload.wikimedia.org/wikipedia/commons/4/4b/Peanut_butter_chocolate_chip_cookies%2C_stacked%2C_November_2009.jpg",
    "fruits & vegetables": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Fresh_Vegetables_display_in_Iloilo_Terminal_Public_Market_11.jpg/500px-Fresh_Vegetables_display_in_Iloilo_Terminal_Public_Market_11.jpg",
    "household": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/66/EFTA00001877_-_Well-organized_pantry_with_Voss_water_bottles_and_cleaning_supplies_featuring_shelves_stocked_with_condiments_jars_and_canned_goods_alongside_a_blue_mop_leaning_against_the_wall.jpg/500px-thumbnail.jpg",
    # croma
    "refrigerator": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Open_refrigerator_with_food_at_night.jpg/500px-Open_refrigerator_with_food_at_night.jpg",
    "television": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c2/Flat_panel_display_image.png/500px-Flat_panel_display_image.png",
    "washing machine": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Front_Load_Washing_Machine.jpg/500px-Front_Load_Washing_Machine.jpg",
    "laptop": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/IBM_Thinkpad_R51.jpg/500px-IBM_Thinkpad_R51.jpg",
    "audio": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Bose_QuietComfort_25_Acoustic_Noise_Cancelling_Headphones_with_Carry_Case.jpg/500px-Bose_QuietComfort_25_Acoustic_Noise_Cancelling_Headphones_with_Carry_Case.jpg",
    "air conditioner": "https://upload.wikimedia.org/wikipedia/commons/8/8b/VRF_System_Concept_%28Multi_Split_System_air_conditioner%29.jpg",
    "smartphone": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Blackview_A60_Smartphone_Android_mobile_phone_front_face_logged_in_screen.jpg/500px-Blackview_A60_Smartphone_Android_mobile_phone_front_face_logged_in_screen.jpg",
}

CONNECTORS = [
    {
        "name": "bigbasket",
        "adapter_path": "wrapper.adapters.bigbasket:BigBasketAdapter",
        "base_url": "http://127.0.0.1:9001",
        "auth": {},
        "description": "BigBasket — groceries, fresh produce, dairy, staples, snacks, household supplies",
        "enabled": True,
    },
    {
        "name": "croma",
        "adapter_path": "wrapper.adapters.croma:CromaAdapter",
        "base_url": "http://127.0.0.1:9002",
        "auth": {},
        "description": "Croma — electronics and appliances: refrigerators, TVs, washing machines, laptops, phones, audio, ACs",
        "enabled": True,
    },
]


# each retailer keeps its own product table ("separate databases"):
# (table, data.json path, native id field, native category field)
CATALOGS = [
    ("bigbasket_products", "mocks/bigbasket/data.json", "sku_id", "cat"),
    ("croma_products", "mocks/croma/data.json", "code", "category"),
]


def main() -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (see .env)")
    client = create_client(url, key)

    for table, path, id_field, cat_field in CATALOGS:
        products = json.loads((ROOT / path).read_text())["products"]
        rows = [{"id": p[id_field], "native": p,
                 "image_url": CATEGORY_IMAGES.get(p[cat_field])} for p in products]
        client.table(table).upsert(rows).execute()
        print(f"upserted {len(rows)} rows into {table}")

    client.table("connectors").upsert(CONNECTORS).execute()
    print(f"upserted {len(CONNECTORS)} connectors: " + ", ".join(c["name"] for c in CONNECTORS))


if __name__ == "__main__":
    main()
