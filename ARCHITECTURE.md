# Tata Node — Architecture

## The one-paragraph version

There is **one node API** (the "Tata Neu UCP node", FastAPI on **:8000**). Users sign
in with **Supabase Auth** (email/password); every call carries their JWT, and carts
and orders are per-user rows in **Supabase Postgres**. An LLM shopping agent (the chat
frontend) never talks to retailers — or the LLM provider — directly: chat goes through
the node's `POST /api/chat` proxy (ONE server-side key for all accounts), and shopping
goes through the node's UCP-shaped endpoints (`/ucp/v1/search`, `/ucp/v1/cart/...`,
`/ucp/v1/checkout`, `/ucp/v1/orders`). Inside the node, a **connector registry**
(loaded from the `connectors` table at startup) knows every attached backend. For each
request, the node decides which retailer should handle it (an LLM call for search
routing; the item's origin for cart/checkout), translates the request into that
retailer's *native* API format, calls the retailer service over HTTP
(**mock BigBasket :9001**, **mock Croma :9002** — later: real digieca/ashiyana APIs),
and normalizes the native response back into one universal UCP shape.

```
┌───────────────────────────┐
│  Chat frontend (:8000/)   │  Gemini-replica UI · Supabase login (JWT)
│  tool-execution loop only │  tools: search_tata_catalog, add_to_cart,
└───────────┬───────────────┘         view_cart, checkout
            │  /api/chat (LLM proxy) + UCP requests · Bearer JWT
            ▼
┌────────────────────────────────────────────────────────┐     ┌────────────────────┐
│  Tata Neu UCP node  (wrapper/, FastAPI :8000)          │────►│ Supabase Postgres  │
│                                                        │     │  auth.users        │
│  /api/chat ─► llm.chat() — server-side key, streaming  │     │  user_carts/orders │
│  /ucp/v1/search ──► 4-stage pipeline                   │     │  catalog_cache     │
│     receive ─► translate ─► enhance ─► respond         │     │  connectors        │
│                  │ (LLM routes to a connector)         │     │  bigbasket_* /     │
│  /ucp/v1/cart/items ─► adapter cart_create/cart_add    │     │  croma_* ("their   │
│  /ucp/v1/checkout ───► adapter place_order + pay       │     │  own databases")   │
│                                                        │     └─────────▲──────────┘
│  adapters/ — RetailerAdapter class per backend,        │               │
│  registry loaded from the connectors table             │               │
└──────────┬──────────────────────┬──────────────────────┘               │
           │ native HTTP          │ native HTTP                          │
           ▼                      ▼                                      │
┌─────────────────────┐    ┌──────────────────────────┐   catalogs + native
│ Mock BigBasket:9001 │    │ Mock Croma :9002         │   carts/orders ────┘
│ RPC-style, snake    │    │ REST-style, camelCase    │
│ cart.create/.add    │    │ POST /cart, /entries     │
│ order.place         │    │ POST /orders             │
│ payment.process     │    │ POST /payments           │
└─────────────────────┘    └──────────────────────────┘
```

## Components

### 1. Chat frontend (`frontend/`)
Static HTML/JS served by the node at `/`. A Gemini-replica chat gated by a
**Supabase login overlay** (supabase-js, config from `/api/config`). The browser
never holds an LLM key: each turn goes to `POST /api/chat` with the user's JWT.
When the **Tata Neu connector** is selected from the **+** popover, the node adds
four tool declarations server-side; tool calls come back to the browser and are
executed against the node's UCP endpoints (same JWT — that's what makes carts
per-user); results are fed back to the LLM and rendered as product cards (with
images from the catalog) / order notes. Deselecting the connector returns to
plain chat.

### 2. Tata Neu UCP node (`wrapper/`) — the core
- **`main.py`** — assembles the app and loads the connector registry at startup.
  The surface (all `/ucp/*` and `/api/chat` require `Authorization: Bearer <jwt>`,
  verified by `auth.py` against the Supabase secret/JWKS):

  | Endpoint | What it does |
  |---|---|
  | `POST /api/chat` | LLM proxy — server-side key, streaming, tool declarations live here |
  | `POST /ucp/v1/search` | Runs the 4-stage search pipeline |
  | `POST /ucp/v1/cart/items` | Adds an item to **the caller's** cart; opens/uses a native cart at the item's retailer |
  | `GET /ucp/v1/cart` | The caller's UCP cart view + which native carts are open |
  | `POST /ucp/v1/checkout` | Places a **native order + payment per retailer**, returns one consolidated confirmation |
  | `GET /ucp/v1/orders` | The caller's past confirmations |
  | `GET /api/config` | Public boot config: Supabase URL + anon key, model name. Never LLM keys |

- **`pipeline.py`** — the 4-stage search pipeline, each stage traced (timings are
  returned in the response for inspection; the UI shows a friendly loader instead):
  1. **receive** — validate/normalize the UCP request
  2. **translate** — an LLM (Claude or Gemini, `llm.py`) picks the retailer and
     extracts structured params (search term, max price, capacity...); the adapter
     builds the retailer's native request
  3. **enhance** — fields the retailer left blank (e.g. Croma's `color: null`) are
     filled via the LLM's web-search tool, marked `enhanced_fields`
  4. **respond** — everything normalized into UCP items
- **`adapters/`** — the connector layer. `base.py` defines the
  `RetailerAdapter` contract: `search` (required), `cart_create` / `cart_add` /
  `place_order` / `pay` (optional — search-only backends get a clean `501` from
  the cart routes), plus declarative `intent_fields` (extra structured search
  params fed into the translate prompt) and `enhance_spec` (which blank field
  the enhance stage may fill, and how). `registry.py` reads the enabled rows
  from the Supabase `connectors` table at startup and instantiates each row's
  `adapter_path` class with its `base_url` + `auth` (secret values come from
  env vars named in the row — never stored in the DB).
  **Attaching a backend (digieca, ashiyana, …) = one adapter file + one row.**
- **`llm.py`** — provider-agnostic LLM client (Anthropic SDK or Gemini REST).
  Hard per-call timeouts; any failure raises `LLMError` — no fallbacks. The
  pipeline treats translate as essential (fails the search with a clear error)
  and enhance as optional (items ship unenriched). `chat()` runs the /api/chat
  turns (history + tool declarations, streaming).
- **`auth.py` / `db.py`** — the Supabase JWT dependency and the shared
  service-role client.

### 3. Mock retailer backends (`mocks/`)
Two standalone FastAPI services with deliberately **different** API conventions, to
prove the adapter layer earns its keep:

| | BigBasket (:9001) | Croma (:9002) |
|---|---|---|
| Style | RPC verbs, POST-everything | RESTful resources |
| Naming | `snake_case`, `sp`/`mrp` | `camelCase`, nested `price` objects |
| Search | `POST /bb/api/v1/product.search` | `GET /croma/api/v2/products/search?text=...` |
| Cart | `cart.create`, `cart.add`, `cart.get` | `POST /cart`, `POST /cart/{id}/entries` |
| Order | `order.place` | `POST /orders` |
| Payment | `payment.process` → `BBTXN-...` | `POST /payments` → `CRMPAY-...` |
| Envelope | `{"status": "success", ...}` | `{"status": 200/201, ...}` |

## The two end-to-end flows

**Search** — *"fridge 200L+ under ₹30,000"*
1. Frontend LLM emits `search_tata_catalog(query, max_price)`
2. Node `translate` stage (its own LLM call) → `{retailer: "croma", search_term,
   maxPrice: 30000, minCapacityLitres: 200}`
3. Croma adapter → `GET :9002/croma/api/v2/products/search?...`
4. `enhance` fills `color_options` where Croma returned `null`
5. UCP items + pipeline trace → frontend renders cards

**Cart → checkout** — *"add the LG fridge and 2L milk, check out"*
1. `add_to_cart(CRM-301202)` → node opens `CRMCART-…` at Croma, `POST /entries`
2. `add_to_cart(BB-40000111)` → node opens `BBCART-…` at BigBasket, `cart.add`
3. `checkout()` → node, per retailer: place native order (`CRMORD-…`, `BBORD-…`),
   then process native payment (`CRMPAY-…` CHARGED, `BBTXN-…` SUCCESS)
4. Node returns one consolidated UCP confirmation: `TATA-…` with
   `retailer_orders[]`, grand total, NeuCoins

## State (Supabase Postgres)

- **Node**: `user_carts` (one row per user: `items` + `native_carts` map),
  `user_orders` (past confirmations), and `catalog_cache` — every item any
  search returned, global, so `add_to_cart` can resolve ids across restarts.
- **Mocks**: each retailer has its **own tables** (`bigbasket_products/_carts/
  _orders`, `croma_*`) as if it ran its own database. Routers keep in-memory
  dicts as a cache, loaded at startup and written through on every mutation —
  the node holds no retailer internals, exactly like production would.
- Everything survives free-tier restarts; auth is Supabase (JWT per request).

## What "UCP-shaped" means here

Every node response uses one universal vocabulary regardless of retailer:
`{ucp_version, type: search_result|cart|order_confirmation, items[], price:
{amount, mrp, currency}, availability, source: {retailer, native_id}, trace[]}`.
The agent only ever learns one schema; retailers keep their native ones.
