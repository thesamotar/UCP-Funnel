/* Gemini-replica chat with a Tata Neu connector.
 * Works with either LLM provider — paste a Gemini key (AIza...) or a
 * Claude key (sk-ant-...) and the chat routes to that API.
 *
 * Connector OFF  -> plain LLM chat.
 * Connector ON   -> the LLM gets UCP tool declarations; tool calls are
 *                   executed against the Tata node (this same origin).
 */

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models";
const ANTHROPIC_BASE = "https://api.anthropic.com/v1/messages";
let GEMINI_MODEL = "gemini-2.5-flash";
let ANTHROPIC_MODEL = "claude-opus-4-8";

const KEYS = { gemini: "", anthropic: "" };
let providerName = null; // "gemini" | "anthropic"
let connectorOn = false;
let history = []; // neutral turns: {role:'user'|'model', text?, toolCalls?, toolResults?}
let busy = false;
let callSeq = 0;

const $ = (id) => document.getElementById(id);

// ---------- tool declarations (neutral) ----------
const TOOL_DEFS = [
  {
    name: "search_tata_catalog",
    description: "Search products across Tata retail brands (BigBasket groceries, Croma electronics). The Tata node routes the query to the right retailer automatically. Use for any shopping/product query.",
    properties: {
      query: { type: "string", description: "Natural-language product query, keep the user's constraints in it, e.g. 'refrigerator 200L+ capacity under 30000'" },
      max_price: { type: "number", description: "Maximum price in INR, if the user stated one" },
      min_price: { type: "number", description: "Minimum price in INR, if stated" },
    },
    required: ["query"],
  },
  {
    name: "add_to_cart",
    description: "Add a product to the Tata Neu cart. item_id must come from a previous search_tata_catalog result.",
    properties: {
      item_id: { type: "string", description: "Product id from search results, e.g. 'CRM-301201'" },
      quantity: { type: "number", description: "Quantity, default 1" },
    },
    required: ["item_id"],
  },
  {
    name: "view_cart",
    description: "View the current Tata Neu cart contents and total.",
    properties: {},
    required: [],
  },
  {
    name: "checkout",
    description: "Place the order for everything in the Tata Neu cart. Ask the user to confirm before calling this.",
    properties: {},
    required: [],
  },
];

const SYSTEM_CONNECTED = `You are a helpful assistant with the Tata Neu connector enabled. You can shop across
Tata brands (BigBasket for groceries, Croma for electronics) via tools. For any product/shopping request, call
search_tata_catalog. Present results conversationally and concisely — the UI already renders product
cards, so summarize/recommend rather than listing every spec. Always use ₹ for prices. Refer to
products by their id (e.g. CRM-301201) when adding to cart. Confirm with the user before checkout.`;

const CATEGORY_EMOJI = {
  refrigerator: "🧊", television: "📺", "washing machine": "🫧", laptop: "💻",
  audio: "🎧", "air conditioner": "❄️", smartphone: "📱", dairy: "🥛",
  eggs: "🥚", bakery: "🍞", staples: "🌾", beverages: "☕", snacks: "🍪",
  "fruits & vegetables": "🥦", household: "🧴",
};

// ---------- boot ----------
(async function boot() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    if (cfg.gemini_model) GEMINI_MODEL = cfg.gemini_model;
    if (cfg.anthropic_model) ANTHROPIC_MODEL = cfg.anthropic_model;
    KEYS.gemini = cfg.gemini_key || "";
    KEYS.anthropic = cfg.anthropic_key || "";
  } catch { /* wrapper not reachable — localStorage only */ }
  KEYS.gemini = KEYS.gemini || localStorage.getItem("gemini_key") || "";
  KEYS.anthropic = KEYS.anthropic || localStorage.getItem("anthropic_key") || "";
  setProvider(localStorage.getItem("provider"));

  $("key-save").onclick = () => saveKey($("key-input").value.trim());
  $("key-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveKey($("key-input").value.trim());
  });
  $("plus-btn").onclick = (e) => { e.stopPropagation(); togglePopover(); };
  document.addEventListener("click", (e) => {
    if (!$("connector-popover").contains(e.target)) hidePopover();
  });
  document.querySelector('[data-connector="tataneu"]').onclick = () => { setConnector(!connectorOn); hidePopover(); };
  $("chip-remove").onclick = () => setConnector(false);
  $("send-btn").onclick = send;
  $("prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
})();

function saveKey(key) {
  if (!key) return;
  if (key.startsWith("sk-ant-")) {
    KEYS.anthropic = key;
    localStorage.setItem("anthropic_key", key);
    setProvider("anthropic");
  } else if (key.startsWith("AIza")) {
    KEYS.gemini = key;
    localStorage.setItem("gemini_key", key);
    setProvider("gemini");
  } else {
    $("key-input").value = "";
    $("key-input").placeholder = "Key must start with AIza... (Gemini) or sk-ant-... (Claude)";
    return;
  }
  $("key-input").value = "";
  $("key-banner").classList.add("hidden");
}

function setProvider(preferred) {
  const candidates = [preferred, "anthropic", "gemini"].filter((p) => p && KEYS[p]);
  providerName = candidates[0] || null;
  if (providerName) {
    localStorage.setItem("provider", providerName);
    $("model-chip").textContent = providerName === "anthropic"
      ? `Claude · ${ANTHROPIC_MODEL.replace("claude-", "")}`
      : `Gemini · ${GEMINI_MODEL.replace("gemini-", "")}`;
    $("key-banner").classList.add("hidden");
  } else {
    $("model-chip").textContent = "no key";
    $("key-banner").classList.remove("hidden");
  }
}

function togglePopover() {
  $("connector-popover").classList.toggle("hidden");
  $("plus-btn").classList.toggle("open");
}
function hidePopover() {
  $("connector-popover").classList.add("hidden");
  $("plus-btn").classList.remove("open");
}
function setConnector(on) {
  connectorOn = on;
  $("tataneu-check").classList.toggle("hidden", !on);
  $("active-chip").classList.toggle("hidden", !on);
  $("prompt").placeholder = on ? "Ask anything · Tata Neu connected" : "Ask anything";
  note(on ? "Tata Neu connector enabled — shopping queries now route through the Tata UCP node"
          : "Tata Neu connector disabled — back to plain chat");
}

// ---------- rendering ----------
function scroll() { $("chat").scrollTop = $("chat").scrollHeight; }

function md(text) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^\s*[*-]\s+/gm, "• ");
}

function addMsg(role, text, opts = {}) {
  $("greeting")?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}${connectorOn ? "" : " plain"}`;
  const who = role === "user" ? "U" : (connectorOn ? "T" : "✦");
  div.innerHTML = `<div class="who">${who}</div><div class="bubble${opts.thinking ? " thinking" : ""}"></div>`;
  div.querySelector(".bubble").innerHTML = opts.thinking ? text : md(text);
  $("messages").appendChild(div);
  scroll();
  return div;
}

function note(text) {
  $("greeting")?.remove();
  const div = document.createElement("div");
  div.className = "tool-note";
  div.innerHTML = text;
  $("messages").appendChild(div);
  scroll();
}

function renderTrace(result) {
  if (!result.trace) return;
  const steps = result.trace.map((t) => `<span class="stage">${t.stage}</span> ${t.detail} <i>(${t.ms}ms)</i>`).join("<br>");
  note(`<b>Tata UCP node pipeline</b> → routed to <b>${result.routed_to}</b><br>${steps}`);
}

function renderCards(items) {
  if (!items?.length) return;
  const grid = document.createElement("div");
  grid.className = "cards";
  for (const it of items) {
    const emoji = CATEGORY_EMOJI[it.attributes?.category] || "🛍️";
    const attrs = Object.entries(it.attributes || {})
      .filter(([k]) => k !== "category")
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(", ") : v}`)
      .join(" · ");
    const enhanced = it.enhanced_fields?.length
      ? `<span class="badge">✦ ${it.enhanced_fields.join(", ")} enriched by node</span>` : "";
    const oos = it.availability !== "in_stock" ? `<span class="oos">out of stock</span>` : "";
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="thumb">${emoji}</div>
      <div class="title">${it.title}</div>
      <div class="price">₹${it.price.amount.toLocaleString("en-IN")}<span class="mrp">₹${it.price.mrp.toLocaleString("en-IN")}</span></div>
      <div class="attrs">${it.id} · ${it.source.retailer}</div>
      <div class="attrs">${attrs}</div>
      ${enhanced}${oos}`;
    grid.appendChild(card);
  }
  $("messages").appendChild(grid);
  scroll();
}

// ---------- tool execution against the Tata node ----------
async function executeTool(name, args) {
  const post = (url, body) => fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(async (r) => ({ ok: r.ok, data: await r.json() }));

  if (name === "search_tata_catalog") {
    const constraints = {};
    if (args.max_price != null) constraints.max_price = args.max_price;
    if (args.min_price != null) constraints.min_price = args.min_price;
    const { data } = await post("/ucp/v1/search", { query: args.query, constraints });
    renderTrace(data);
    renderCards(data.items);
    const { trace, native_request, ...forModel } = data; // keep the model payload lean
    return forModel;
  }
  if (name === "add_to_cart") {
    const { ok, data } = await post("/ucp/v1/cart/items", { item_id: args.item_id, quantity: args.quantity || 1 });
    note(ok ? `Added <b>${args.item_id}</b> to Tata Neu cart · total ₹${data.total.amount.toLocaleString("en-IN")}` : `add_to_cart failed: ${data.detail}`);
    return data;
  }
  if (name === "view_cart") {
    return (await fetch("/ucp/v1/cart")).json();
  }
  if (name === "checkout") {
    const { ok, data } = await post("/ucp/v1/checkout", {});
    note(ok ? `🎉 Order <b>${data.order_id}</b> placed · ₹${data.total.amount.toLocaleString("en-IN")} · +${data.neu_coins_earned} NeuCoins` : `checkout failed: ${data.detail}`);
    if (ok) for (const ro of data.retailer_orders || []) {
      note(`↳ ${ro.retailer} order <b>${ro.order_id}</b> · ₹${ro.amount.toLocaleString("en-IN")} · payment <b>${ro.payment.status}</b> (${ro.payment.payment_id} via ${ro.payment.method})`);
    }
    return data;
  }
  return { error: `unknown tool ${name}` };
}

// ---------- provider adapters ----------
// Both take the neutral history and return {text, toolCalls: [{id, name, args}]}.

async function callGemini() {
  const contents = [];
  for (const turn of history) {
    if (turn.role === "user" && turn.text != null) {
      contents.push({ role: "user", parts: [{ text: turn.text }] });
    } else if (turn.role === "model") {
      const parts = [];
      if (turn.text) parts.push({ text: turn.text });
      for (const c of turn.toolCalls || []) parts.push({ functionCall: { name: c.name, args: c.args } });
      contents.push({ role: "model", parts });
    } else if (turn.toolResults) {
      contents.push({
        role: "user",
        parts: turn.toolResults.map((r) => ({ functionResponse: { name: r.name, response: { result: r.result } } })),
      });
    }
  }
  const body = { contents, generationConfig: { temperature: 0.7 } };
  if (connectorOn) {
    body.tools = [{
      functionDeclarations: TOOL_DEFS.map((t) => ({
        name: t.name,
        description: t.description,
        parameters: { type: "OBJECT", properties: t.properties, required: t.required },
      })),
    }];
    body.systemInstruction = { parts: [{ text: SYSTEM_CONNECTED }] };
  }
  const resp = await fetch(`${GEMINI_BASE}/${GEMINI_MODEL}:generateContent?key=${KEYS.gemini}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Gemini API ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
  const data = await resp.json();
  const parts = data.candidates?.[0]?.content?.parts || [];
  return {
    text: parts.filter((p) => p.text).map((p) => p.text).join(""),
    toolCalls: parts.filter((p) => p.functionCall)
      .map((p) => ({ id: `call_${++callSeq}`, name: p.functionCall.name, args: p.functionCall.args || {} })),
  };
}

async function callClaude() {
  const messages = [];
  for (const turn of history) {
    if (turn.role === "user" && turn.text != null) {
      messages.push({ role: "user", content: turn.text });
    } else if (turn.role === "model") {
      const content = [];
      if (turn.text) content.push({ type: "text", text: turn.text });
      for (const c of turn.toolCalls || []) content.push({ type: "tool_use", id: c.id, name: c.name, input: c.args });
      messages.push({ role: "assistant", content });
    } else if (turn.toolResults) {
      messages.push({
        role: "user",
        content: turn.toolResults.map((r) => ({
          type: "tool_result", tool_use_id: r.id, content: JSON.stringify(r.result),
        })),
      });
    }
  }
  const body = { model: ANTHROPIC_MODEL, max_tokens: 8192, messages };
  if (connectorOn) {
    body.system = SYSTEM_CONNECTED;
    body.tools = TOOL_DEFS.map((t) => ({
      name: t.name,
      description: t.description,
      input_schema: { type: "object", properties: t.properties, required: t.required },
    }));
  }
  const resp = await fetch(ANTHROPIC_BASE, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": KEYS.anthropic,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Claude API ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
  const data = await resp.json();
  return {
    text: (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join(""),
    toolCalls: (data.content || []).filter((b) => b.type === "tool_use")
      .map((b) => ({ id: b.id, name: b.name, args: b.input || {} })),
  };
}

async function callLLM() {
  if (providerName === "anthropic") return callClaude();
  if (providerName === "gemini") return callGemini();
  throw new Error("No API key configured");
}

// ---------- chat loop ----------
async function send() {
  const text = $("prompt").value.trim();
  if (!text || busy) return;
  if (!providerName) { $("key-banner").classList.remove("hidden"); return; }
  $("prompt").value = "";
  busy = true;
  addMsg("user", text);
  history.push({ role: "user", text });
  const pending = addMsg("model", "Thinking…", { thinking: true });

  try {
    for (let turn = 0; turn < 6; turn++) {
      const { text: modelText, toolCalls } = await callLLM();
      history.push({ role: "model", text: modelText, toolCalls });
      if (!toolCalls.length) {
        pending.querySelector(".bubble").innerHTML = md(modelText || "(empty response)");
        pending.querySelector(".bubble").classList.remove("thinking");
        break;
      }
      if (modelText) note(md(modelText));
      const results = [];
      for (const call of toolCalls) {
        note(`⚙️ <b>${call.name}</b>(${JSON.stringify(call.args)})`);
        pending.remove(); // tool notes/cards take its place mid-flight
        const result = await executeTool(call.name, call.args);
        results.push({ id: call.id, name: call.name, result });
      }
      history.push({ role: "user", toolResults: results });
      $("messages").appendChild(pending); // re-attach for the next model turn
      scroll();
    }
  } catch (err) {
    pending.querySelector(".bubble").innerHTML = md(`**Error:** ${err.message}`);
    pending.querySelector(".bubble").classList.remove("thinking");
  } finally {
    busy = false;
  }
}
