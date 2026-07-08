# Tata Node — Agentic Commerce Wrapper (UCP Funnel)

## What this is

Imagine you're chatting with an AI assistant and you say *"buy me a fridge over
200 litres for under ₹30,000."* Today the assistant can't really *do* that — at
best it scrapes a website and hopes the layout hasn't changed. **This project is
the missing piece in the middle:** a single "node" API that sits between the AI
and Tata's shops (BigBasket for groceries, Croma for electronics) and lets the AI
**search → add to cart → pay** using one clean, universal language instead of
scraping.

That universal language is **UCP** (Universal Commerce Protocol). The AI only ever
learns *one* vocabulary; the node does the messy work of translating each request
into whatever format each individual shop actually speaks, and translating the
replies back.

**In plain terms:**
- The **AI shopping agent** (a Gemini-style chat window) is the customer's mouth.
- The **Tata Node** is a universal translator + concierge.
- The **mock shops** (BigBasket, Croma) are the actual stores, each with its own
  quirky in-house API — exactly like real retailers, which never agree on
  formats.

**In technical terms:** a FastAPI "wrapper" service exposes UCP-shaped endpoints
(`/ucp/v1/search`, `/ucp/v1/cart/items`, `/ucp/v1/checkout`). Internally it runs an
LLM-driven routing + enrichment pipeline for search, and per-retailer adapters that
speak each backend's native REST/RPC dialect for cart, order, and payment. Two
standalone FastAPI mocks stand in for the real BigBasket and Croma backends.

This is a **48-hour demo**, not production — it favours a working end-to-end slice
over completeness, and keeps dependencies minimal.

```
Chat frontend (Gemini or Claude)         ← the AI shopping agent
        │  UCP requests
        ▼
Tata Neu UCP node  (:8000)               ← the universal translator
   search → route → enrich → respond
   cart / order / payment  → adapters
        │                    │
        ▼ native APIs        ▼ native APIs
  Mock BigBasket (:9001)   Mock Croma (:9002)   ← the actual stores
  RPC · snake_case         REST · camelCase
  28 grocery SKUs          25 electronics SKUs
```

> A deeper component-by-component breakdown lives in
> [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Setup

**Requirements:** Python 3.11+, and one LLM API key (either a Claude key
`sk-ant-...` **or** a Gemini key `AIza...`). Node.js is optional (only used if you
want to re-run the JS syntax check).

```bash
cd "Tata Node"

# 1. Create a virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Provide ONE LLM key (either works — the app auto-detects which)
export ANTHROPIC_API_KEY=sk-ant-...     # OR:
export GEMINI_API_KEY=AIza...
#   (a .env file in this folder is also picked up automatically)

# 3. Start all three services (mock shops + node + frontend)
./run.sh

# 4. Open the demo
#    http://localhost:8000
```

`run.sh` launches three processes: **mock BigBasket** on `:9001`, **mock Croma** on
`:9002`, and the **Tata Neu node** (which also serves the chat UI) on `:8000`.

**Which brain runs where.** Both the node's internal reasoning *and* the chat
frontend accept either key:
- A **Claude** key → chat runs on `claude-opus-4-8`; the node enriches missing
  product fields via Claude's web-search tool.
- A **Gemini** key → chat runs on `gemini-2.5-flash` + Google Search grounding.
- If both are set, `LLM_PROVIDER=anthropic|gemini` picks the node's brain, and you
  can paste either key into the UI banner (it detects the provider by prefix).
- With **no key at all**, everything still runs — routing and enrichment fall back
  to deterministic keyword heuristics — but the chat window itself needs a key.

### Demo script (the 60-second walkthrough)

1. Open http://localhost:8000 and paste your key in the banner.
2. Ask something with the connector **off** → plain chat, no shopping powers.
3. Click the **+** next to the input → select **Tata Neu** in the connector popup.
4. Ask: *"I want a refrigerator of 200L+ capacity under ₹30,000."*
   → routed to **Croma**, product cards appear, missing colours filled in by the
   node, and the pipeline trace shows each stage.
5. Ask: *"order 2 litres of milk"* → same tool, routed to **BigBasket** instead.
6. *"Add the LG fridge and the milk to my cart, then check out."*
   → the node opens a real cart at *each* shop, places an order at each, pays at
   each, and returns one combined confirmation with NeuCoins.
7. Deselect Tata Neu → prompts go back to plain chat.

---

## Project layout

| Path | What it is |
|---|---|
| `frontend/` | Gemini-replica chat UI; + connector menu; dual-provider (Gemini/Claude) tool-calling loop |
| `wrapper/main.py` | Assembles the UCP node: includes the action routers and mounts the frontend |
| `wrapper/routes/` | One module per action exposing an `APIRouter`: `config.py`, `search.py`, `cart.py`, `checkout.py` |
| `wrapper/state.py` | Shared in-memory node state (UCP cart, catalog cache, orders) + the cart-view helper |
| `wrapper/pipeline.py` | The 4-stage search pipeline (receive → translate → enhance → respond) with per-stage trace |
| `wrapper/fallback/` | Deterministic no-LLM fallbacks (keyword routing + canned colors), isolated so the whole folder can be deleted once the LLM path is reliable — see its README |
| `wrapper/adapters.py` | One entry per retailer — search + cart + order + payment, each in the retailer's native dialect. **Adding a Tata brand = adding one entry here** |
| `wrapper/llm.py` | Provider-agnostic LLM client (Claude via Anthropic SDK, or Gemini via REST) with graceful fallback |
| `mocks/bigbasket/` | Mock BigBasket — RPC style, snake_case, `sp`/`mrp` pricing. Routes split per operation: `search.py`, `cart.py`, `order.py`, `payment.py`, wired up in `app.py` (shared state in `store.py`) |
| `mocks/croma/` | Mock Croma — REST style, camelCase, nested price objects; some `color: null` on purpose. Same per-operation split: `search.py` / `cart.py` / `order.py` / `payment.py` / `app.py` / `store.py` |
| `ARCHITECTURE.md` | Full architecture write-up with diagrams and both end-to-end flows |

---

## Changelog

### v0.1 — Search slice (2026-07-07)

**In plain terms:** built the whole skeleton and got *search* working end to end —
you can ask the AI for a product, it figures out which shop sells it, asks that
shop, tidies up the answer (even filling in details the shop forgot to send, like
colour options), and shows you neat product cards.

**What landed, technically:**
- **Two mock retailer services** (FastAPI) with deliberately *different* API
  conventions so the translation layer has something real to do:
  BigBasket (POST search, snake_case, `sp`/`mrp`) and Croma (GET search with query
  params, camelCase, nested `searchResult` envelope). ~28 grocery + ~25 electronics
  SKUs. A few Croma products ship `specs.color = null` on purpose.
- **The UCP node** with a **4-stage search pipeline**:
  1. *receive* — validate/normalise the incoming UCP request.
  2. *translate* — an LLM decides which retailer handles the query and extracts
     structured parameters (search term, max price, capacity…); the matching
     adapter builds the retailer's native request.
  3. *enhance* — fields the retailer left blank (e.g. Croma colour options) are
     filled in via the LLM's web-search / grounding, tagged `enhanced_fields`.
  4. *respond* — everything normalised into one UCP item shape, with a per-stage
     timing trace returned for transparency.
- **Provider-agnostic LLM client** — works with **either a Claude key or a Gemini
  key**, auto-selected by which is present (`LLM_PROVIDER` breaks ties). Falls back
  to deterministic keyword routing/enrichment when no key is set, so the demo never
  hard-fails.
- **Gemini-replica chat frontend** with a ChatGPT-style **+ connector menu**.
  Selecting **Tata Neu** routes every prompt through the node with tool
  declarations (`search_tata_catalog`, `add_to_cart`, `view_cart`, `checkout`);
  deselecting returns to plain chat. The UI detects a Gemini (`AIza…`) or Claude
  (`sk-ant-…`) key by prefix and calls the right API directly from the browser
  (Claude uses the official browser-access header).
- Cart and checkout existed but were **in-memory stubs** at this stage — no real
  retailer round-trip yet.

### v0.2 — Commerce slice: cart, orders & payments (2026-07-08)

**In plain terms:** made buying *actually happen*. Before, "add to cart" and
"checkout" were faked inside the node. Now each shop has its own real cart, order,
and payment counter — and when you check out, the node walks up to *each* shop
separately, places your order there, pays there, and hands you one combined
receipt. If you've got a fridge from Croma and milk from BigBasket in the same
cart, that's two real orders and two real payments, stitched into a single
confirmation.

**What landed, technically:**
- **Full commerce APIs on both mocks**, each in its own realistic dialect:
  - *BigBasket* — RPC verbs: `cart.create` → `cart.add` → `order.place` →
    `payment.process`; ids like `BBORD-…` / `BBTXN-…`; `{"status":"success"}`
    envelopes; guards for out-of-stock, missing cart, empty cart, double-pay.
  - *Croma* — RESTful resources: `POST /cart` → `POST /cart/{id}/entries` →
    `POST /orders` → `POST /payments`; ids like `CRMORD-…` / `CRMPAY-…`; numeric
    status codes; order status `PAYMENT_PENDING → CONFIRMED`.
- **Cart/order/payment adapters in the node** that normalise each retailer's flow
  to a common shape (`cart_create` → `cart_add` → `place_order` → `pay`), so the
  node's logic never has to know a retailer's quirks.
- **The node's cart & checkout now delegate to real retailer calls** instead of
  faking them:
  - `add_to_cart` lazily opens a **native cart at the item's own retailer** and
    adds the item there; the UCP cart mirrors it. A single UCP cart can therefore
    hold open carts at multiple shops at once.
  - `checkout` places one **native order + payment per retailer** and returns a
    consolidated confirmation (`retailer_orders[]`, each with its native order id
    and payment receipt, plus a grand total and NeuCoins).
  - Retailer-side failures (e.g. out of stock) surface as clean `502`s with the
    native message.
- **Frontend** now renders the per-retailer order/payment breakdown under the
  combined confirmation.
- **`ARCHITECTURE.md`** added — a full write-up of the components, the two
  end-to-end flows (search, and cart→checkout), and the demo-grade shortcuts.

### v0.3 — Mock restructure + env-based keys (2026-07-09)

**In plain terms:** housekeeping, no behaviour change. Each mock shop used to be
one long file; now every shop is its own folder with a separate file per action
(search, cart, order, payment), so it's obvious where each API lives. Also moved
API keys out of the homepage box and into a `.env` file you fill in once.

**What landed, technically:**
- **Split each mock into a package** — `mocks/bigbasket/` and `mocks/croma/`,
  each with one module per operation (`search.py`, `cart.py`, `order.py`,
  `payment.py`) exposing a FastAPI `APIRouter`, assembled in `app.py`. Shared
  catalog data and in-memory cart/order state moved to a per-service `store.py`;
  each `*_data.json` moved into its folder as `data.json`. **All URL paths are
  unchanged**, so the node and adapters are unaffected.
- `run.sh` uvicorn targets updated to `mocks.bigbasket.app:app` /
  `mocks.croma.app:app`; old `mocks/bigbasket_api.py` and `mocks/croma_api.py`
  removed.
- **`.env` support** — `run.sh` already sources `.env`; added a committed
  `.env.example` template (`ANTHROPIC_API_KEY` / `GEMINI_API_KEY`) so keys live in
  a gitignored `.env` instead of being pasted on the homepage. The frontend reads
  them via `/api/config` on load.
- Verified end to end after the move: direct search on both mocks, and the full
  cart → order → payment flow on each retailer.

### v0.4 — Wrapper restructure (2026-07-09)

**In plain terms:** same housekeeping, now for the node itself. Every UCP API
used to live in one `main.py`; each action is now its own file, and `main.py`
just wires them together. No behaviour change.

**What landed, technically:**
- **Split the UCP node's endpoints into `wrapper/routes/`** — one module per
  action, each exposing a FastAPI `APIRouter`: `config.py` (`/api/config`),
  `search.py` (`/ucp/v1/search`), `cart.py` (`/ucp/v1/cart/items` + `/ucp/v1/cart`),
  `checkout.py` (`/ucp/v1/checkout`).
- **Shared in-memory state moved to `wrapper/state.py`** — the UCP cart, catalog
  cache, and orders list, plus the `cart_view()` helper that add-to-cart, cart
  view, and checkout all reuse. Modules import these by reference and only mutate
  their contents, so they stay in sync.
- **`main.py` is now just an assembler** — includes the four routers and mounts
  the frontend; `pipeline.py` / `adapters.py` / `llm.py` are unchanged. Route
  paths and `wrapper.main:app` are unchanged, so `run.sh` and the frontend are
  unaffected.
- Verified end to end after the move: config, search (populates the cache),
  add-to-cart, cart view, checkout (per-retailer order + payment, then cart
  cleared), the unknown-item 404 guard, and the frontend still served at `/`.

### v0.5 — Isolate the no-LLM fallbacks (2026-07-09)

**In plain terms:** the demo has deterministic stand-ins so it runs even with no
API key — keyword-based shop routing and canned color options. Those were mixed
into the pipeline; they're now quarantined in one folder you can delete in a
single move once the real LLM path is reliable.

**What landed, technically:**
- **New `wrapper/fallback/` package** holding every deterministic fallback:
  `routing.py` (`fallback_route()` + the BigBasket/Croma keyword hint tables) and
  `colors.py` (`fallback_colors()` + the canned `FALLBACK_COLORS` table). Its
  `README.md` documents the exact removal steps.
- **`pipeline.py` now imports from it** at three spots, each tagged `# [FALLBACK]`:
  the import, the translate-stage routing fallback, and the enhance-stage color
  fallback. Nothing else references the package, so removal = `rm -rf
  wrapper/fallback` + deleting those three marked lines/blocks.
- Behaviour unchanged. Verified with no working key (placeholder): grocery query
  keyword-routes to BigBasket, electronics to Croma (reason "keyword fallback"),
  and Croma color gaps fill from the canned table.

---

## Demo-grade shortcuts (deliberate)

- One in-memory UCP cart; the mocks keep their own in-memory carts/orders.
  Everything resets on restart. No sessions or auth.
- `/api/config` hands the server's LLM keys to the browser — **localhost only**.
- Payments are mock counters — no real gateway, no money moves.
- Only *search* runs the 4-stage pipeline (that's the scoped focus); cart/checkout
  are direct adapter calls.
