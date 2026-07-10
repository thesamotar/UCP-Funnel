# Filling data for the mock retailer APIs

The mock retailers (BigBasket :9001, Croma :9002) no longer read their
catalogs from disk at runtime — they load them from Supabase at startup. Each
retailer has its **own** set of tables, as if each company ran its own
database: `bigbasket_products` / `bigbasket_carts` / `bigbasket_orders` and
`croma_products` / `croma_carts` / `croma_orders`. The node never reads these;
only the mock services do. This file explains where the product data comes
from and how to add, edit, or re-source it.

## The pipeline

```
mocks/<retailer>/data.json    ←  source of truth, edited by hand, lives in git
        │
        ▼  python -m db.seed        (idempotent upsert; re-run after any edit)
<retailer>_products (Supabase) ←  what the mocks actually serve
        │
        ▼  loaded at mock startup (restart the services to pick up changes)
mock search/cart/order APIs
```

`db/seed.py` reads both `data.json` files, wraps each product as
`{id, native, image_url}` and upserts into that retailer's `_products` table.
The `native` column holds the product **exactly** in that retailer's own API
shape — the mocks serve it verbatim, the wrapper's adapter normalizes it.

## Product row formats

Each mock keeps its deliberately different native convention:

**BigBasket** (`mocks/bigbasket/data.json`, snake_case RPC style):

```json
{"sku_id": "BB-40000111", "desc": "Amul Taaza Toned Milk 1L", "brand": "Amul",
 "cat": "dairy", "sp": 68, "mrp": 72, "pack_size": "1 L",
 "availability": "A", "img": "<ignored — image_url column wins>"}
```

Required: `sku_id` (unique, `BB-…`), `desc`, `brand`, `cat`, `sp` (selling
price), `mrp`, `pack_size`, `availability` (`"A"` in stock / `"O"` out).

**Croma** (`mocks/croma/data.json`, camelCase REST style):

```json
{"code": "CRM-301201", "name": "Samsung 236L ... Refrigerator", "brandName": "Samsung",
 "category": "refrigerator", "price": {"mrp": 32990, "sellingPrice": 27990},
 "specs": {"capacity": "236 L", "energyRating": "3 Star", "color": "Elegant Inox"},
 "inStock": true, "imageUrl": "<ignored — image_url column wins>"}
```

Required: `code` (unique, `CRM-…`), `name`, `brandName`, `category`,
`price.mrp` + `price.sellingPrice`, `specs` (free-form), `inStock`.
Setting `specs.color` to `null` is intentional in some rows — it exercises the
wrapper's LLM enhance stage, which fills the gap as `color_options`.

## Product images

Images shown in the frontend product cards come from the `image_url` column,
seeded from the `CATEGORY_IMAGES` map at the top of `db/seed.py` — currently
one representative Wikimedia Commons photo per category (each URL verified to
serve an image). Categories without a decent match (`dairy`, `bakery`,
`staples`) are deliberately unmapped; the card falls back to the category
emoji.

To improve images:

- **Per category**: add/replace an entry in `CATEGORY_IMAGES` with any stable
  public image URL, re-run `python -m db.seed`, restart the services.
- **Per product** (best for a real demo): upload photos to a public Supabase
  Storage bucket (Dashboard → Storage → new bucket, tick *Public*), then set
  each row's `image_url` to the file's public URL — either straight in the
  Table Editor or by extending `seed.py` with a `PRODUCT_IMAGES = {"CRM-301201":
  "https://<project>.supabase.co/storage/v1/object/public/products/fridge.jpg"}`
  override. No code changes needed; the frontend just renders whatever
  `image_url` holds.
- Hotlinking rules of thumb: Wikimedia Commons and Supabase Storage allow it;
  most retailer CDNs (croma.com, bigbasket.com) block cross-origin hotlinks —
  don't point at those.

## Adding a whole new catalog (new retailer / attached API)

Real attached APIs (digieca, ashiyana) own their own data — nothing to seed.
Only add data here when you're building another *mock*:

1. Create `mocks/<name>/data.json` in whatever native shape that API uses.
2. Add its tables to `db/schema.sql` (`<name>_products` / `_carts` / `_orders`,
   copy the bigbasket block) and run that SQL in Supabase.
3. Add one entry to `CATALOGS` in `db/seed.py` (table, json path, id field,
   category field) and, if needed, new `CATEGORY_IMAGES` entries.
4. Add the connector row (see `CONNECTORS` in `seed.py`) pointing at its
   adapter class and base URL.
5. `python -m db.seed`, restart.

## Gotchas

- `python -m db.seed` needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
  exported (`set -a; source .env; set +a`).
- Seeding only *upserts* — removing a product from `data.json` does not delete
  its row. Delete stale rows in the Supabase Table Editor (or truncate the
  `_products` table and re-seed).
- The mocks read the catalog **once at startup**; restart `./run.sh` after
  re-seeding.
- Keep ids unique across retailers (`BB-…` vs `CRM-…` prefixes) — the wrapper's
  `catalog_cache` and cart routes key on the bare id.
