"""Seed the Supabase database from the mock retailers' data.json files.

Run once after applying db/schema.sql:

    .venv/bin/python -m db.seed

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment
(run.sh sources .env; or `set -a; source .env` first).

Idempotent: upserts by primary key, safe to re-run after editing data.json
or the image map below. See db/data_sourcing_mock.md for how to add/replace
catalog data and product images.
"""
from __future__ import annotations

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
    # zudio
    "t-shirts": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Blue_Tshirt.jpg/500px-Blue_Tshirt.jpg",
    "jeans": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/Jeans.jpg/500px-Jeans.jpg",
    "dresses": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/91/Woman_in_a_dress.jpg/500px-Woman_in_a_dress.jpg",
    "jackets": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Leather_jacket.jpg/500px-Leather_jacket.jpg",
    "sneakers": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/Sneakers.jpg/500px-Sneakers.jpg",
    "activewear": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Yoga_pants.jpg/500px-Yoga_pants.jpg",
    "loungewear": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Pajamas.jpg/500px-Pajamas.jpg",
    "accessories": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Sunglasses.jpg/500px-Sunglasses.jpg",
    "innerwear": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f6/Underwear.jpg/500px-Underwear.jpg",
    "winterwear": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/Sweater.jpg/500px-Sweater.jpg",
    # cliq
    "smartphones": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Blackview_A60_Smartphone_Android_mobile_phone_front_face_logged_in_screen.jpg/500px-Blackview_A60_Smartphone_Android_mobile_phone_front_face_logged_in_screen.jpg",
    "laptops": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/IBM_Thinkpad_R51.jpg/500px-IBM_Thinkpad_R51.jpg",
    "watches": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/Watch.jpg/500px-Watch.jpg",
    "shoes": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/Shoes.jpg/500px-Shoes.jpg",
    "fragrances": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Perfume_bottle.jpg/500px-Perfume_bottle.jpg",
    "handbags": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/59/Handbag.jpg/500px-Handbag.jpg",
    "sunglasses": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Sunglasses.jpg/500px-Sunglasses.jpg",
    "grooming": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7c/Shaving_brush.jpg/500px-Shaving_brush.jpg",
    "ethnicwear": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Saree.jpg/500px-Saree.jpg",
    "westernwear": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Blue_Tshirt.jpg/500px-Blue_Tshirt.jpg",
    # onemg
    "medicines": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Pills.jpg/500px-Pills.jpg",
    "supplements": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Vitamins.jpg/500px-Vitamins.jpg",
    "vitamins": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Vitamins.jpg/500px-Vitamins.jpg",
    "ayurveda": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Ayurveda_herbs.jpg/500px-Ayurveda_herbs.jpg",
    "devices": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f6/Thermometer.jpg/500px-Thermometer.jpg",
    "personal_care": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Soap.jpg/500px-Soap.jpg",
    "baby_care": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/Baby_bottle.jpg/500px-Baby_bottle.jpg",
    "homeopathy": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Pills.jpg/500px-Pills.jpg",
    "nutrition": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Protein_powder.jpg/500px-Protein_powder.jpg",
    "sexual_wellness": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Condom.jpg/500px-Condom.jpg",
    # titan
    "analog_watches": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/Watch.jpg/500px-Watch.jpg",
    "smartwatches": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2d/Smartwatch.jpg/500px-Smartwatch.jpg",
    "gold_jewelry": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Gold_necklace.jpg/500px-Gold_necklace.jpg",
    "diamond_jewelry": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Diamond_ring.jpg/500px-Diamond_ring.jpg",
    "eyeglasses": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/Glasses.jpg/500px-Glasses.jpg",
    "perfumes": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Perfume_bottle.jpg/500px-Perfume_bottle.jpg",
    "wall_clocks": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f4/Wall_clock.jpg/500px-Wall_clock.jpg",
    "belts": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3c/Leather_belt.jpg/500px-Leather_belt.jpg",
    "wallets": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Wallet.jpg/500px-Wallet.jpg",
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
    {
        "name": "zudio",
        "adapter_path": "wrapper.adapters.zudio:ZudioAdapter",
        "base_url": "http://127.0.0.1:9003",
        "auth": {},
        "description": "Zudio — fast fashion, apparel, t-shirts, jeans, dresses, shoes",
        "enabled": True,
    },
    {
        "name": "cliq",
        "adapter_path": "wrapper.adapters.cliq:CliqAdapter",
        "base_url": "http://127.0.0.1:9004",
        "auth": {},
        "description": "Tata CLiQ — premium lifestyle, fashion, luxury, apparel, footwear, accessories",
        "enabled": True,
    },
    {
        "name": "onemg",
        "adapter_path": "wrapper.adapters.onemg:OneMgAdapter",
        "base_url": "http://127.0.0.1:9005",
        "auth": {},
        "description": "Tata 1mg — pharmacy, medicines, supplements, healthcare, ayurveda, baby care",
        "enabled": True,
    },
    {
        "name": "titan",
        "adapter_path": "wrapper.adapters.titan:TitanAdapter",
        "base_url": "http://127.0.0.1:9006",
        "auth": {},
        "description": "Titan — watches, jewelry, smartwatches, sunglasses, perfumes, gold",
        "enabled": True,
    },
]


# each retailer keeps its own product table ("separate databases"):
# (table, data.json path, native id field, native category field)
CATALOGS = [
    ("bigbasket_products", "mocks/bigbasket/data.json", "sku_id", "cat"),
    ("croma_products", "mocks/croma/data.json", "code", "category"),
    ("zudio_products", "mocks/zudio/data.json", "code", "category"),
    ("cliq_products", "mocks/cliq/data.json", "code", "category"),
    ("onemg_products", "mocks/onemg/data.json", "code", "category"),
    ("titan_products", "mocks/titan/data.json", "code", "category"),
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
