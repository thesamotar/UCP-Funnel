from __future__ import annotations

import json
import os
import random

def generate_zudio():
    categories = ["t-shirts", "jeans", "dresses", "jackets", "sneakers", "activewear", "loungewear", "accessories", "innerwear", "winterwear"]
    colors = ["Black", "White", "Blue", "Red", "Olive", "Grey"]
    sizes = ["XS", "S", "M", "L", "XL"]
    products = []
    count = 1
    for cat in categories:
        for i in range(7):
            products.append({
                "id": f"ZUD-{count:03d}",
                "type": "product",
                "attributes": {
                    "name": f"Zudio {cat.capitalize()} {i+1}",
                    "category": cat,
                    "price": random.choice([299, 499, 799, 999]),
                    "sizes": sizes,
                    "color": random.choice(colors),
                    "stock": random.randint(10, 100)
                }
            })
            count += 1
    return {"products": products}

def generate_cliq():
    categories = ["smartphones", "laptops", "watches", "shoes", "fragrances", "handbags", "sunglasses", "grooming", "ethnicwear", "westernwear"]
    brands = ["Apple", "Samsung", "Fossil", "Puma", "Versace", "Baggit", "Ray-Ban", "Philips", "Biba", "Levis"]
    products = []
    count = 1
    for i, cat in enumerate(categories):
        brand = brands[i]
        for j in range(7):
            mrp = random.randint(1000, 50000)
            salePrice = int(mrp * random.uniform(0.6, 0.9))
            products.append({
                "sku": f"CLQ-{count:03d}",
                "title": f"{brand} {cat.capitalize()} Model {j+1}",
                "category": cat,
                "brand": brand,
                "pricing": {"mrp": mrp, "salePrice": salePrice},
                "attributes": {"color": random.choice(["Black", "Silver", "Gold", "White"])},
                "inventory": random.randint(5, 50)
            })
            count += 1
    return {"products": products}

def generate_onemg():
    categories = ["medicines", "supplements", "vitamins", "ayurveda", "devices", "personal_care", "baby_care", "homeopathy", "nutrition", "sexual_wellness"]
    brands = ["1mg", "Dabur", "Himalaya", "Patanjali", "Accu-Chek", "Nivea", "Johnson", "SBL", "Ensure", "Durex"]
    products = []
    count = 1
    for i, cat in enumerate(categories):
        brand = brands[i]
        for j in range(7):
            mrp = random.randint(50, 1500)
            price = int(mrp * random.uniform(0.8, 0.95))
            products.append({
                "item_id": f"1MG-{count:03d}",
                "name": f"{brand} {cat.capitalize()} Product {j+1}",
                "category": cat,
                "brand": brand,
                "price": price,
                "mrp": mrp,
                "pack_size": random.choice(["1 unit", "10 tablets", "200 ml", "500g"]),
                "prescription_required": cat == "medicines",
                "in_stock": True
            })
            count += 1
    return {"products": products}

def generate_titan():
    categories = ["analog_watches", "smartwatches", "gold_jewelry", "diamond_jewelry", "sunglasses", "eyeglasses", "perfumes", "wall_clocks", "belts", "wallets"]
    brands = ["Titan", "Fastrack", "Tanishq", "Mia", "Skinn", "Sonata", "Helios"]
    products = []
    count = 1
    for cat in categories:
        for j in range(7):
            brand = random.choice(brands)
            mrp = random.randint(1500, 50000)
            products.append({
                "productId": f"TTN-{count:03d}",
                "productName": f"{brand} {cat.capitalize()} {j+1}",
                "category": cat,
                "brand": brand,
                "price": mrp,
                "mrp": mrp,
                "specs": {
                    "dialColor": random.choice(["Black", "Blue", "White", "Rose Gold"]),
                    "strapMaterial": random.choice(["Leather", "Metal", "Silicone"])
                },
                "stock": True
            })
            count += 1
    return {"products": products}

def main():
    mocks = {
        "zudio": generate_zudio(),
        "cliq": generate_cliq(),
        "onemg": generate_onemg(),
        "titan": generate_titan()
    }
    
    for mock_name, data in mocks.items():
        dir_path = f"mocks/{mock_name}"
        os.makedirs(dir_path, exist_ok=True)
        with open(f"{dir_path}/data.json", "w") as f:
            json.dump(data, f, indent=2)
        print(f"Generated {len(data['products'])} products for {mock_name}")

if __name__ == "__main__":
    main()
