# Tata Node — Agentic Commerce Wrapper (UCP Funnel)

**Version 1.1** (2026-07-18) — see the [changelog](#changelog).

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
   cart / order  → adapters
   payment → UPI QR via Razorpay (test)
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

**Requirements:** Python 3.11+, one LLM API key (either a Claude key
`sk-ant-...` **or** a Gemini key `AIza...`), a free
[Supabase](https://supabase.com) project (database + auth), and free
[Razorpay](https://dashboard.razorpay.com) **test-mode** API keys (the UPI
payment step — no KYC needed for test mode).

```bash
cd "Tata Node"

# 1. Create a virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Create the Supabase project (one-time)
#    - dashboard → New project (free tier)
#    - SQL Editor → paste db/schema.sql → Run
#    - Authentication → Sign In / Providers → Email → disable "Confirm email"
#      (demo convenience; leave on if you don't mind the confirmation step)
#    - Project Settings → API: copy the URL + anon key + service_role key

# 3. Get Razorpay TEST keys (one-time)
#    - dashboard.razorpay.com → sign up → toggle Test Mode on (top bar)
#    - Account & Settings → API Keys → Generate Test Key
#    - copy the rzp_test_… Key Id and the Key Secret (shown only once)

# 4. Fill .env (copy .env.example): ONE LLM key + Supabase + Razorpay values
cp .env.example .env   # then edit

# 5. Seed the retailer catalogs + connector registry into Supabase (one-time,
#    re-run after editing mocks/*/data.json — see db/data_sourcing_mock.md)
set -a; source .env; set +a
.venv/bin/python -m db.seed

# 6. Start all three services (mock shops + node + frontend)
./run.sh

# 7. Open the demo and create an account
#    http://localhost:8000
```

`run.sh` launches three processes: **mock BigBasket** on `:9001`, **mock Croma** on
`:9002`, and the **Tata Neu node** (which also serves the chat UI) on `:8000`.

**One brain, server-side.** A single server-side key powers everything for every
signed-in account — the browser never sees an LLM key; chat goes through
`POST /api/chat`:
- A **Claude** key → chat and node run on `ANTHROPIC_MODEL` (default
  `claude-sonnet-5`); the node enriches missing product fields via Claude's
  web-search tool.
- A **Gemini** key → chat and node run on `GEMINI_MODEL` (default
  `gemini-2.5-flash`) + Google Search grounding.
- If both are set, `LLM_PROVIDER=anthropic|gemini` picks.
- A key is **required** — there is no non-LLM fallback. If the LLM can't be
  reached, search fails fast with a clear error instead of pretending to work.
- Every LLM call has a hard timeout (`LLM_TIMEOUT_S` 25s; search-grounded
  enrichment `LLM_SEARCH_TIMEOUT_S` 45s; chat turns `LLM_CHAT_TIMEOUT_S` 60s),
  and the whole search pipeline runs under one deadline (`SEARCH_DEADLINE_S`,
  default 100s → `504`).

**Accounts.** Supabase Auth (email/password). Every UCP call carries the user's
JWT; carts and orders are per-user and persist in Postgres across restarts.
Product catalogs are public.

**Payments.** When the user says the order is complete, the node creates a
**Razorpay payment link** (test mode) for the exact cart total and the chat
shows it as a **scannable UPI QR**. The app polls Razorpay until the link is
`paid`, then places the retailer orders — checkout **requires** a
Razorpay-verified payment matching the cart total; there is no mock fallback.
In test mode, complete the payment via Razorpay's simulated checkout (e.g.
Netbanking → demo bank → **Success**); no real money moves.

### Demo script (the 60-second walkthrough)

1. Open http://localhost:8000 and sign in (or create an account).
2. Ask something with the connector **off** → plain chat, no shopping powers.
3. Click the **+** next to the input → select **Tata Neu** in the connector popup.
4. Ask: *"I want a refrigerator of 200L+ capacity under ₹30,000."*
   → routed to **Croma**, product cards appear, missing colours filled in by the
   node, and the pipeline trace shows each stage.
5. Ask: *"order 2 litres of milk"* → same tool, routed to **BigBasket** instead.
6. *"Add the LG fridge and the milk to my cart. That's all — I'm ready to pay."*
   → a **UPI QR for the exact total** appears in the chat ("Waiting for
   payment…"). Scan it with a phone or click *open the payment page*, complete
   the test payment (Netbanking → demo bank → **Success**), and the card flips
   to "✅ Payment received" — the node then places a real order at *each* shop
   and the assistant posts one combined confirmation with NeuCoins.
7. Deselect Tata Neu → prompts go back to plain chat.

---

## Project layout

| Path | What it is |
|---|---|
| `frontend/` | Gemini-replica chat UI: Google-style Supabase sign-in, connector menu (Tata Neu logo), tool-calling loop against the node (LLM via `/api/chat`) |
| `wrapper/main.py` | Assembles the UCP node: loads the connector registry at startup, includes the action routers, mounts the frontend |
| `wrapper/routes/` | One module per action exposing an `APIRouter`: `config.py`, `chat.py` (LLM proxy), `search.py`, `cart.py`, `payment.py` (UPI QR + status polling), `checkout.py` |
| `wrapper/state.py` | Per-user node state in Supabase (carts, orders) + the global catalog cache and cart-view helper |
| `wrapper/auth.py` | `current_user` dependency — verifies the Supabase JWT on every UCP/chat call |
| `wrapper/db.py` | Shared async Supabase client (service-role key) |
| `wrapper/pipeline.py` | The 4-stage search pipeline (receive → translate → enhance → respond), registry-driven, with per-stage trace |
| `wrapper/adapters/` | `base.py` (the `RetailerAdapter` contract), one adapter class per backend (`bigbasket.py`, `croma.py`), `registry.py` (loads enabled connectors from the DB). **Attaching an API = one adapter file + one `connectors` row** |
| `wrapper/llm.py` | Provider-agnostic LLM client (Claude via Anthropic SDK, or Gemini via REST) — hard per-call timeouts, failures raise `LLMError`; `chat()` powers `/api/chat` |
| `wrapper/razorpay.py` | Razorpay Payment Links client (test mode): create a link for the cart total, poll its status — HTTP basic auth, no webhooks needed |
| `db/` | `schema.sql` (all Supabase tables + RLS), `seed.py` (catalogs + connector registry), `data_sourcing_mock.md` (how to fill mock data & images) |
| `mocks/bigbasket/` | Mock BigBasket — RPC style, snake_case, `sp`/`mrp` pricing. Routes split per operation: `search.py`, `cart.py`, `order.py`, `payment.py`, wired up in `app.py`; `store.py` loads its own Supabase tables (`bigbasket_*`) |
| `mocks/croma/` | Mock Croma — REST style, camelCase, nested price objects; some `color: null` on purpose. Same split; `store.py` loads `croma_*` tables |
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

### v0.6 — LLM-only pipeline, timeouts & clean loading UX (2026-07-10)

**In plain terms:** removed the training wheels and fixed the freeze. The node
now *always* uses the real LLM — no more canned stand-ins quietly covering for
it — and nothing can hang forever: every step has a deadline, and if the LLM
can't answer in time you get a clear error instead of an endless spinner. The
chat also stopped showing its plumbing (`⚙️ search_tata_catalog(...)`, pipeline
traces); you now see a spinner with friendly status texts while the node works.

**What landed, technically:**
- **Root-caused the "stuck" search**: the enhance stage called Anthropic's
  web-search tool *non-streaming*; those long requests get dropped upstream and
  the SDK's default timeout is 10 minutes — the pipeline sat silent. (Earlier it
  only "worked" because failures were swallowed and the fallback filled canned
  colors.) All Anthropic calls now **stream**, which fixes web search
  (~35s, verified).
- **`wrapper/fallback/` deleted** along with its pipeline hooks. `llm.py` no
  longer swallows errors: failures raise `LLMError`. Translate is essential —
  failure surfaces as a `502` with the reason; enhance is optional — failure
  ships items unenriched (never fabricated data). No key configured = clear
  `502 no LLM key configured`, not a silent heuristic.
- **Timeout guardrails at every layer**: per-LLM-call (`LLM_TIMEOUT_S` 25s /
  `LLM_SEARCH_TIMEOUT_S` 45s), whole-pipeline (`SEARCH_DEADLINE_S` 100s → `504`),
  and browser-side `AbortSignal.timeout` on both the chat-model calls (60s) and
  node calls (110s) with a friendly "took too long" message.
- **Frontend hides the machinery**: pipeline trace and tool-call notes are gone
  (the trace still travels in the API response for debugging); a spinner with
  rotating static texts ("Searching across Tata stores…", "Placing your
  order…") shows while tools run. Node errors now reach the model as `{error}`
  results so it can respond honestly.
- **Deploy prep**: `/api/config` only exposes server keys when
  `EXPOSE_CONFIG_KEYS=1` (kept on in the local `.env`), and a `render.yaml`
  Blueprint deploys the whole demo as one free-tier Render web service.

### v0.7 — Supabase database, user accounts & the connector registry (2026-07-11)

**In plain terms:** the demo grew a real memory and a front door. Product
catalogs, carts, and orders now live in a proper database (Supabase Postgres)
instead of files and RAM — so nothing is lost when the free-tier server naps.
You sign in with an email and password, and *your* cart is yours: two people
shopping at once no longer share a basket. And the node's shop list is no
longer hard-coded — new backends (digieca, ashiyana…) plug in with one small
adapter file and one database row.

**What landed, technically:**
- **Supabase Postgres** (`db/schema.sql`, seeded by `db/seed.py`): per-retailer
  "own databases" (`bigbasket_products/_carts/_orders`, `croma_*`) that only the
  mocks touch, plus the node's tables — `user_carts`, `user_orders` (per-user),
  `catalog_cache` (global id→item resolution), and `connectors` (the registry).
  RLS on everything; only the `_products` tables are publicly readable.
- **Supabase Auth**: email/password login in the frontend (supabase-js); every
  UCP/chat call carries the session JWT, verified server-side (`wrapper/auth.py`,
  HS256 secret or JWKS — no per-request network hop). Carts/orders keyed by user.
- **LLM proxy** (`POST /api/chat`): the browser no longer calls
  Anthropic/Gemini directly with a pasted key — ONE server-side key powers all
  accounts; tool declarations and the system prompt moved server-side. Anthropic
  calls stream with wall-clock caps, same as the pipeline. `EXPOSE_CONFIG_KEYS`
  is gone.
- **Connector registry** (`wrapper/adapters/`): `RetailerAdapter` base class
  (search required; cart/order/payment optional — search-only backends get a
  clean `501`), per-backend adapter classes, and a registry loaded from the
  `connectors` table at startup. Adapters declare their own extra intent params
  and enhance rules, so `pipeline.py` has zero retailer-specific code.
  **Attaching a new API = one adapter file + one DB row.**
- **Mocks are DB-backed**: catalogs load from each retailer's `_products` table
  at startup (no more `data.json` at runtime — it's the seed source); carts and
  orders write through to `_carts`/`_orders`, so native state survives restarts
  mid-session.
- **Frontend**: a full-page branded sign-in (feature panel, password
  visibility toggle, animated backdrop) gates the chat — the app shell only
  renders once supabase-js has a session; sign-out returns to the login page.
  Product cards now show real images (`image_url` seeded per category, emoji
  fallback); `GET /ucp/v1/orders` lists the signed-in user's past orders.

### v0.7.1 — Static-asset cache fix (2026-07-11)

**In plain terms:** after the v0.7 login page shipped, a browser that had
visited the demo before could show a completely broken sign-in screen — no
styling, dead buttons. The page itself was fine; the browser was pairing the
*new* HTML with *old* cached CSS/JS. Fixed so browsers always pick up the
latest files.

**What landed, technically:**
- The frontend mount now serves everything with `Cache-Control: no-cache`
  (`NoCacheStaticFiles` in `wrapper/main.py`) — browsers revalidate on every
  load instead of trusting heuristic freshness, and unchanged files still
  come back as cheap `304`s via the existing ETags.
- `index.html` references its assets with versioned URLs (`style.css?v=8`,
  `app.js?v=8`) so even a browser holding pre-fix cached copies fetches the
  current files on its next reload. Bump `?v=` to force-refresh assets again.

### v1.0 — Gemini-faithful UI (2026-07-11)

**In plain terms:** the demo now *looks* the part. The whole frontend — sign-in
page and chat screen — is a faithful copy of the Gemini UI, with one deliberate
difference: you sign in with an email and password (Supabase) instead of a
Google account. The one visible tell that this isn't Google's product is the
Tata Neu connector, which now wears the real Tata Neu logo.

**What landed, technically:**
- **Sign-in page rebuilt in the Google accounts style**: a single dark rounded
  card with the Gemini spark mark, "Sign in — Use your Tata Neu account to
  continue to Gemini", outlined text fields, a text-button "Create account" on
  the left and a filled blue pill "Sign in" on the right. Replaces the v0.7
  branded panel (orbs, feature list, purple gradients). Auth logic is
  unchanged — same Supabase email/password flow, password-visibility toggle,
  and sign-in/sign-up mode switch.
- **Gemini dark theme site-wide**: `#131314` background palette, and the site
  font switched from Inter to **Google Sans** (served by the Google Fonts css2
  API), so every element — including the connector status notes, which were
  previously monospace — uses one consistent typeface. Note padding and
  coloring unchanged.
- **Chat screen fidelity**: personalized gradient greeting ("Hello, <name>"
  from the signed-in email), "Ask Gemini" composer placeholder, the model
  avatar is always the Gemini gradient ✦, and the model-name chip next to the
  "Gemini" wordmark is gone.
- **Connectors**: the placeholder Google Drive row is removed; the Tata Neu
  connector row and active-connector chip show the real Tata Neu logo, served
  locally from `frontend/tata-neu-logo.png` (no third-party hotlinking).
- Fixed the stacked (narrow-viewport) sign-in layout not spanning full width;
  assets bumped to `?v=9`.

### v1.1 — Real UPI payment step via Razorpay test mode (2026-07-18)

**In plain terms:** paying is no longer pretend. When you tell the assistant
your order is complete, a **UPI QR code for the exact cart total** appears
right in the chat. Scan it (or open the payment page), pay, and the moment the
money clears the order places itself and the assistant confirms — you never
click a checkout button. It runs on Razorpay's test mode, so the whole flow is
real gateway plumbing with no actual money moving.

**What landed, technically:**
- **Razorpay Payment Links integration** (`wrapper/razorpay.py`): test-mode
  keys from `.env` (`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`), HTTP basic auth,
  15s timeouts. No webhooks — status is polled, which works locally without a
  public URL.
- **New payment routes** (`wrapper/routes/payment.py`):
  `POST /ucp/v1/payment/initiate` creates a payment link for the caller's cart
  total and returns it with a server-generated QR (pure-Python `segno`, data
  URI — the QR encodes the link's `short_url`, so scanning opens Razorpay's
  checkout on the phone); `GET /ucp/v1/payment/{id}` proxies live status.
- **Checkout now demands proof of payment**: `POST /ucp/v1/checkout` takes a
  `payment_link_id`, re-fetches it from Razorpay server-side, and only places
  retailer orders if the link is `paid` **and** the paid amount matches the
  current cart total in paise (`409` if the cart changed after the QR was
  issued, `402` if unpaid, `503` if Razorpay keys aren't configured — per the
  no-fallback rule, there is no mock-payment path). The confirmation now
  carries a `upi_payment` block with the Razorpay payment id.
- **The LLM's `checkout` tool became `initiate_payment`** — the model detects
  "my order is complete / I want to pay" intent, confirms the total, and
  triggers the QR; the system prompt forbids claiming the order is placed
  until payment is confirmed.
- **Frontend payment card + poller** (`frontend/app.js`): renders the QR,
  amount, payment-page link, and a live status line; polls every 3s (8-minute
  cap) and on `paid` flips to "✅ Payment received", calls checkout with the
  link id, renders the per-retailer confirmation notes, and fires a hidden
  follow-up turn so the assistant posts the confirmation message itself.
  Assets bumped to `?v=10`.
- Verified end to end against live Razorpay test mode: intent → QR →
  simulated payment on the hosted checkout → poll → order placed → chat
  confirmation. Test-mode quirk worth knowing: Razorpay's hosted page offers
  Cards/Netbanking/Wallet on an unactivated test account (UPI as a *method*
  appears once the account is activated) — the QR/link/poll flow is identical
  either way.

---

## Demo-grade shortcuts (deliberate)

- The **customer payment** is a real gateway flow (Razorpay, test mode — no
  money moves); the **retailer-side** order/payment counters at BigBasket and
  Croma are still mocks, settled instantly once the Razorpay payment clears.
- Only *search* runs the 4-stage pipeline (that's the scoped focus); cart/checkout
  are direct adapter calls.
- The chat proxy trusts the browser's tool-execution loop (tools run client-side
  against the node with the user's own JWT).
- One shared LLM key serves all accounts — no per-user quotas/limits.
- Mock product images are one representative photo per category (see
  `db/data_sourcing_mock.md` for upgrading to per-product images).

---

## Hosting (free tier)

The repo ships a [`render.yaml`](render.yaml) Blueprint for **Render's free
tier** — the best free fit here because the demo is three processes, and a
Render web service is a full container that can run all of them (the mocks stay
on container-private ports; only the node binds the public `$PORT`).

1. Create the Supabase project, run `db/schema.sql`, and seed (Setup steps 2–4).
2. Push the repo to GitHub.
3. Render dashboard → **New → Blueprint** → pick the repo.
4. Fill the secrets when prompted: `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY`),
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `RAZORPAY_KEY_ID` + `RAZORPAY_KEY_SECRET` (test keys), and optionally
   `SUPABASE_JWT_SECRET`.
5. Open `https://tata-node.onrender.com` (or whatever name Render assigns) and
   create an account.

Free-tier caveats: the Render service spins down after ~15 min idle (first
request cold-starts in ~1 min) — but users, carts, orders, and catalogs live in
Supabase, so nothing is lost. Supabase's free tier pauses the project after
~1 week with no traffic; resume it from the dashboard. Alternatives that also
work: Hugging Face Spaces (Docker, no spin-down, needs a small Dockerfile) or
Railway (trial credit, not permanently free). Vercel/Netlify don't fit —
they're serverless and can't run the three long-lived processes.
