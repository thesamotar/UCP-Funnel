# Tata Node — Architecture

## The one-paragraph version

There is **one node API** (the "Tata Neu UCP node", FastAPI on **:8000**). An LLM
shopping agent (the chat frontend) never talks to retailers directly — it calls the
node's UCP-shaped endpoints (`/ucp/v1/search`, `/ucp/v1/cart/...`, `/ucp/v1/checkout`).
Inside the node, a single **adapter registry** knows every Tata retailer backend. For
each request, the node decides which retailer should handle it (an LLM call for search
routing; the item's origin for cart/checkout), translates the request into that
retailer's *native* API format, calls the mock retailer service over HTTP
(**BigBasket :9001**, **Croma :9002**), and normalizes the native response back into
one universal UCP shape.

```
┌─────────────────────────┐
│  Chat frontend (:8000/) │  Gemini-replica UI · Gemini OR Claude key
│  LLM + tool declarations│  tools: search_tata_catalog, add_to_cart,
└───────────┬─────────────┘         view_cart, checkout
            │  UCP requests (JSON over HTTP, same origin)
            ▼
┌───────────────────────────────────────────────────────┐
│  Tata Neu UCP node  (wrapper/, FastAPI :8000)         │
│                                                       │
│  /ucp/v1/search ──► 4-stage pipeline                  │
│     receive ─► translate ─► enhance ─► respond        │
│                  │ (LLM routes to a retailer)         │
│  /ucp/v1/cart/items ─► adapter cart_create/cart_add   │
│  /ucp/v1/checkout ───► adapter place_order + pay      │
│                                                       │
│  adapters.py — one entry per retailer:                │
│    search · cart_create · cart_add · place_order · pay│
└──────────┬──────────────────────────┬─────────────────┘
           │ native HTTP              │ native HTTP
           ▼                          ▼
┌─────────────────────┐    ┌──────────────────────────┐
│ Mock BigBasket:9001 │    │ Mock Croma :9002         │
│ RPC-style, snake    │    │ REST-style, camelCase    │
│ 28 grocery SKUs     │    │ 25 electronics SKUs      │
│ cart.create/.add    │    │ POST /cart, /entries     │
│ order.place         │    │ POST /orders             │
│ payment.process     │    │ POST /payments           │
└─────────────────────┘    └──────────────────────────┘
```

## Components

### 1. Chat frontend (`frontend/`)
Static HTML/JS served by the node at `/`. A Gemini-replica chat that works with
either a **Gemini** key (`AIza...`) or a **Claude** key (`sk-ant-...`) — detected by
prefix, called directly from the browser. When the **Tata Neu connector** is selected
from the **+** popover, every prompt is sent to the LLM together with four tool
declarations. Tool calls are executed against the node's UCP endpoints; results are
fed back to the LLM and rendered as product cards / order notes. Deselecting the
connector returns to plain chat.

### 2. Tata Neu UCP node (`wrapper/`) — the core
- **`main.py`** — the UCP surface:

  | Endpoint | What it does |
  |---|---|
  | `POST /ucp/v1/search` | Runs the 4-stage search pipeline |
  | `POST /ucp/v1/cart/items` | Adds an item; opens/uses a **native cart at the item's retailer** |
  | `GET /ucp/v1/cart` | UCP cart view + which native carts are open |
  | `POST /ucp/v1/checkout` | Places a **native order + payment per retailer**, returns one consolidated confirmation |
  | `GET /api/config` | Hands the browser the server's LLM keys/models (localhost demo convenience) |

- **`pipeline.py`** — the 4-stage search pipeline, each stage traced (timings are
  returned in the response and rendered in the UI):
  1. **receive** — validate/normalize the UCP request
  2. **translate** — an LLM (Claude or Gemini, `llm.py`) picks the retailer and
     extracts structured params (search term, max price, capacity...); the adapter
     builds the retailer's native request
  3. **enhance** — fields the retailer left blank (e.g. Croma's `color: null`) are
     filled via the LLM's web-search tool, marked `enhanced_fields`
  4. **respond** — everything normalized into UCP items
- **`adapters.py`** — the retailer registry. **Adding a Tata brand = adding one
  entry** with five functions: `search`, `cart_create`, `cart_add`, `place_order`,
  `pay`. Each function speaks the retailer's native dialect and returns a
  normalized shape.
- **`llm.py`** — provider-agnostic LLM client (Anthropic SDK or Gemini REST),
  deterministic keyword/static fallbacks when no key is set.

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

## State (demo-grade, in-memory)

- **Node**: one UCP cart (`items` + `native_carts` map), a catalog cache of every
  item any search returned (so `add_to_cart` can resolve ids), past orders.
- **Mocks**: their own `CARTS` / `ORDERS` dicts — the node holds no retailer
  internals, exactly like production would.
- No sessions/auth; everything resets on restart.

## What "UCP-shaped" means here

Every node response uses one universal vocabulary regardless of retailer:
`{ucp_version, type: search_result|cart|order_confirmation, items[], price:
{amount, mrp, currency}, availability, source: {retailer, native_id}, trace[]}`.
The agent only ever learns one schema; retailers keep their native ones.
