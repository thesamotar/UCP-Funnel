/* Gemini-replica chat with a Tata Neu connector.
 *
 * Auth: Supabase email/password login (supabase-js, config from /api/config).
 * Every node call carries the session JWT — carts and orders are per-user.
 * The LLM runs server-side behind POST /api/chat (one shared key for all
 * accounts); the browser never sees an LLM key.
 *
 * Connector OFF  -> plain LLM chat (still via the node proxy).
 * Connector ON   -> the node adds UCP tool declarations; tool calls come back
 *                   here and are executed against the node's UCP endpoints.
 */

let sb = null;          // supabase-js client
let session = null;     // current auth session (null = signed out)
let authMode = "signin"; // "signin" | "signup"
let connectorOn = false;
let history = []; // neutral turns: {role:'user'|'model', text?, toolCalls?, toolResults?}
let busy = false;

const $ = (id) => document.getElementById(id);

const CATEGORY_EMOJI = {
  refrigerator: "🧊", television: "📺", "washing machine": "🫧", laptop: "💻",
  audio: "🎧", "air conditioner": "❄️", smartphone: "📱", dairy: "🥛",
  eggs: "🥚", bakery: "🍞", staples: "🌾", beverages: "☕", snacks: "🍪",
  "fruits & vegetables": "🥦", household: "🧴",
};

// ---------- boot ----------
(async function boot() {
  const cfg = await (await fetch("/api/config")).json();
  $("model-chip").textContent = cfg.provider === "anthropic"
    ? `Claude · ${(cfg.model || "").replace("claude-", "")}`
    : cfg.provider === "gemini" ? `Gemini · ${(cfg.model || "").replace("gemini-", "")}`
    : "no key";
  if (!cfg.supabase_url || !cfg.supabase_anon_key) {
    note("⚠️ Supabase is not configured on the server — set SUPABASE_URL and SUPABASE_ANON_KEY");
    return;
  }
  sb = supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
  sb.auth.onAuthStateChange((_event, s) => { session = s; renderAuth(); });
  session = (await sb.auth.getSession()).data.session;
  renderAuth();

  // auth form events
  $("auth-form").addEventListener("submit", (e) => { e.preventDefault(); submitAuth(); });
  $("auth-password").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submitAuth(); } });
  $("auth-toggle").onclick = (e) => { e.preventDefault(); setAuthMode(authMode === "signin" ? "signup" : "signin"); };
  $("signout-btn").onclick = () => sb.auth.signOut();

  // password visibility toggle
  $("pw-toggle").onclick = () => {
    const input = $("auth-password");
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    $("pw-eye-show").classList.toggle("hidden", !isPassword);
    $("pw-eye-hide").classList.toggle("hidden", isPassword);
  };

  // connector / chat events
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

// ---------- auth ----------
function renderAuth() {
  const signedIn = !!session;
  // toggle between login page and app shell
  $("auth-page").classList.toggle("hidden", signedIn);
  $("app-shell").classList.toggle("hidden", !signedIn);
  if (signedIn) {
    $("avatar").textContent = session.user.email[0].toUpperCase();
    $("avatar").title = session.user.email;
  }
}

function setAuthMode(mode) {
  authMode = mode;
  const isSignin = mode === "signin";
  $("auth-title").textContent = isSignin ? "Welcome back" : "Create account";
  document.querySelector(".auth-card-sub").textContent = isSignin
    ? "Sign in to continue to your account"
    : "Get started with Tata Neu AI";
  $("auth-submit-text").textContent = isSignin ? "Sign in" : "Create account";
  $("auth-toggle").textContent = isSignin ? "Create one" : "Sign in instead";
  $("auth-switch-text").textContent = isSignin ? "Don't have an account?" : "Already have an account?";
  $("auth-password").setAttribute("autocomplete", isSignin ? "current-password" : "new-password");
  authError("");
}

function authError(text) {
  $("auth-error").textContent = text;
  $("auth-error").classList.toggle("hidden", !text);
}

async function submitAuth() {
  const email = $("auth-email").value.trim();
  const password = $("auth-password").value;
  if (!email || !password) { authError("Email and password are required"); return; }
  $("auth-submit").disabled = true;
  $("auth-submit-text").classList.add("hidden");
  $("auth-spinner").classList.remove("hidden");
  try {
    if (authMode === "signin") {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } else {
      const { data, error } = await sb.auth.signUp({ email, password });
      if (error) throw error;
      if (!data.session) {
        authError("Account created — confirm the email we sent you, then sign in.");
        setAuthMode("signin");
        return;
      }
    }
    authError("");
  } catch (err) {
    authError(err.message || String(err));
  } finally {
    $("auth-submit").disabled = false;
    $("auth-submit-text").classList.remove("hidden");
    $("auth-spinner").classList.add("hidden");
  }
}

async function authHeaders() {
  const s = (await sb.auth.getSession()).data.session; // refreshed by supabase-js when expiring
  if (!s) { renderAuth(); throw new Error("Signed out — sign in to continue"); }
  return { Authorization: `Bearer ${s.access_token}` };
}

// ---------- connector toggle ----------
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
  const who = role === "user" ? ($("avatar").textContent || "U") : (connectorOn ? "T" : "✦");
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

// ---------- loading indicator ----------
// While the node works we show a spinner with friendly static texts instead
// of the technical tool-call/pipeline chatter.
const LOADER_TEXTS = {
  default: ["Thinking…"],
  search_tata_catalog: [
    "Searching across Tata stores…",
    "Matching products to your request…",
    "Fetching live product details…",
    "Almost there…",
  ],
  add_to_cart: ["Adding to your cart…"],
  view_cart: ["Fetching your cart…"],
  checkout: ["Placing your order…", "Processing payment…", "Preparing your receipt…"],
};

let loaderTimer = null;
function setLoader(pendingEl, kind) {
  const texts = LOADER_TEXTS[kind] || LOADER_TEXTS.default;
  const bubble = pendingEl.querySelector(".bubble");
  let i = 0;
  const show = () => { bubble.innerHTML = `<span class="spin"></span>${texts[i++ % texts.length]}`; };
  clearInterval(loaderTimer);
  show();
  loaderTimer = setInterval(show, 2500);
}
function stopLoader() {
  clearInterval(loaderTimer);
  loaderTimer = null;
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
    if (it.image && /^https?:\/\//.test(it.image)) {
      const img = document.createElement("img");
      img.src = it.image;
      img.alt = it.title;
      img.loading = "lazy";
      img.onerror = () => { img.remove(); }; // broken URL -> back to the emoji
      const thumb = card.querySelector(".thumb");
      thumb.classList.add("has-img");
      thumb.appendChild(img);
    }
    grid.appendChild(card);
  }
  $("messages").appendChild(grid);
  scroll();
}

// ---------- tool execution against the Tata node ----------
const NODE_TIMEOUT_MS = 110_000; // just above the node's own search deadline

async function executeTool(name, args) {
  const headers = await authHeaders();
  const post = (url, body) => fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(NODE_TIMEOUT_MS),
  }).then(async (r) => ({ ok: r.ok, data: await r.json() }));

  if (name === "search_tata_catalog") {
    const constraints = {};
    if (args.max_price != null) constraints.max_price = args.max_price;
    if (args.min_price != null) constraints.min_price = args.min_price;
    const { ok, data } = await post("/ucp/v1/search", { query: args.query, constraints });
    if (!ok) return { error: data.detail || "search failed" };
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
    return (await fetch("/ucp/v1/cart", { headers, signal: AbortSignal.timeout(NODE_TIMEOUT_MS) })).json();
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

// ---------- the node's LLM proxy ----------
const LLM_TIMEOUT_MS = 70_000; // just above the node's own chat deadline

async function callNode() {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ history, connector: connectorOn }),
    signal: AbortSignal.timeout(LLM_TIMEOUT_MS),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || `chat failed (${resp.status})`);
  return data; // {text, toolCalls: [{id, name, args}]}
}

// ---------- chat loop ----------
async function send() {
  const text = $("prompt").value.trim();
  if (!text || busy) return;
  if (!session) { renderAuth(); return; }
  $("prompt").value = "";
  busy = true;
  addMsg("user", text);
  history.push({ role: "user", text });
  const pending = addMsg("model", "", { thinking: true });
  setLoader(pending, "default");

  try {
    for (let turn = 0; turn < 6; turn++) {
      const { text: modelText, toolCalls } = await callNode();
      history.push({ role: "model", text: modelText, toolCalls });
      if (!toolCalls.length) {
        stopLoader();
        pending.querySelector(".bubble").innerHTML = md(modelText || "(empty response)");
        pending.querySelector(".bubble").classList.remove("thinking");
        break;
      }
      const results = [];
      for (const call of toolCalls) {
        setLoader(pending, call.name);
        const result = await executeTool(call.name, call.args);
        results.push({ id: call.id, name: call.name, result });
        $("messages").appendChild(pending); // keep the loader below the cards/notes
      }
      history.push({ role: "user", toolResults: results });
      setLoader(pending, "default");
      scroll();
    }
  } catch (err) {
    const message = err.name === "TimeoutError"
      ? "That took too long, so the request was stopped. Please try again."
      : err.message;
    pending.querySelector(".bubble").innerHTML = md(`**Error:** ${message}`);
    pending.querySelector(".bubble").classList.remove("thinking");
  } finally {
    stopLoader();
    busy = false;
  }
}
