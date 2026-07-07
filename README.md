# Tata Node — Agentic Commerce Wrapper (48h demo)

A UCP (Universal Commerce Protocol)-shaped API that sits between an LLM shopping
agent and Tata e-commerce backends, so an agent can **search → cart → checkout**
instead of scraping.

```
Gemini-replica chat  ──►  Tata UCP node (:8000)  ──►  mock BigBasket (:9001)
 (+ Tata Neu connector)     receive → translate           groceries, 28 SKUs
                            → enhance → respond      ──►  mock Croma (:9002)
                                                          electronics, 25 SKUs
```

## Run it

```bash
cd "Tata Node"
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...  # OR export GEMINI_API_KEY=AIza...
./run.sh                             # then open http://localhost:8000
```

**Either LLM key works** — the wrapper and the frontend auto-detect whichever
is set (`.env` file also works). With a Claude key the chat runs on
`claude-opus-4-8` and the node enriches missing fields via Claude's web-search
tool; with a Gemini key it uses `gemini-2.5-flash` + Google Search grounding.
If both are set, `LLM_PROVIDER=anthropic|gemini` picks the wrapper's brain and
you can paste either key in the UI banner (auto-detected by prefix).

Without any key the node still runs — routing and enrichment fall back to
deterministic heuristics — but the chat frontend needs a key (it will ask for
one in a banner and keep it in localStorage).

## The demo script

1. Open http://localhost:8000 — a Gemini-replica chat.
2. Ask something with the connector **off** → plain Gemini, no shopping powers.
3. Click **+** next to the input → select **Tata Neu** in the connector popover.
4. Ask: *"I want to buy a refrigerator of 200L+ capacity under ₹30,000."*
   - the chat LLM (Claude or Gemini) emits a `search_tata_catalog` tool call
   - the node's **translate** stage (its own LLM call) routes it to **Croma**
     and builds Croma's native request (`text`, `maxPrice`, `minCapacityLitres`)
   - the **enhance** stage notices Croma returned `color: null` on some models
     and fills `color_options` via the LLM's web-search tool
   - the **respond** stage normalizes everything to UCP items; the UI shows
     product cards plus the pipeline trace
5. Ask: *"order 2 litres of milk"* → same tool, routed to **BigBasket** instead.
6. *"Add the LG fridge to my cart"* → `add_to_cart`, then *"check out"* →
   `checkout` returns a mock order with NeuCoins.
7. Deselect Tata Neu from the + menu → prompts go back to plain Gemini.

## Pieces

| Path | What |
|---|---|
| `wrapper/main.py` | UCP node: `/ucp/v1/search`, `/ucp/v1/cart(...)`, `/ucp/v1/checkout`; serves the frontend |
| `wrapper/pipeline.py` | The 4-stage search pipeline with per-stage trace |
| `wrapper/adapters.py` | BigBasket + Croma adapters (native request building + UCP normalization). New retailer = new entry here |
| `wrapper/llm.py` | Provider-agnostic LLM client — Claude (Anthropic SDK) or Gemini (REST) — with graceful fallback without a key |
| `mocks/bigbasket_api.py` | Mock BigBasket: `POST /bb/api/v1/product.search`, snake_case, `sp`/`mrp` |
| `mocks/croma_api.py` | Mock Croma: `GET /croma/api/v2/products/search`, camelCase, nested envelope, some `color: null` on purpose |
| `frontend/` | Gemini-replica UI, + connector popover, function-calling loop |

## Demo-grade shortcuts (deliberate)

- One in-memory cart, no sessions/auth; catalog cache backs `add_to_cart`.
- `/api/config` hands the server's LLM keys to the browser — localhost only.
- Checkout is a mock: no payment, order lives in memory.
- Cart/checkout bypass the 4-stage pipeline (it's built for search, per scope).
