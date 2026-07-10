-- Tata Node — Supabase schema. Run once in the Supabase SQL editor
-- (Dashboard → SQL Editor → paste → Run), then seed with `python -m db.seed`.
--
-- All server-side access uses the service-role key (bypasses RLS). RLS is
-- enabled everywhere anyway so the anon/publishable key can read exactly one
-- thing: the product catalog.

-- per-retailer "databases" ------------------------------------------------------
-- Each mock retailer gets its own tables (<name>_products / _carts / _orders),
-- as if each company ran its own database — the node never reads these, only
-- the mock services do. Products are public read; carts/orders are
-- service-role only and exist so native state survives free-tier cold starts.

create table if not exists bigbasket_products (
  id         text primary key,          -- BB sku_id
  native     jsonb not null,            -- the product exactly as BigBasket's native API shape
  image_url  text,                      -- shown on the frontend product card
  updated_at timestamptz not null default now()
);

create table if not exists bigbasket_carts (
  id         text primary key,          -- BBCART-…
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists bigbasket_orders (
  id         text primary key,          -- BBORD-…
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists croma_products (
  id         text primary key,          -- CRM code
  native     jsonb not null,            -- the product exactly as Croma's native API shape
  image_url  text,
  updated_at timestamptz not null default now()
);

create table if not exists croma_carts (
  id         text primary key,          -- CRMCART-…
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists croma_orders (
  id         text primary key,          -- CRMORD-…
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

-- per-user UCP state ----------------------------------------------------------
create table if not exists user_carts (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  items        jsonb not null default '[]',
  native_carts jsonb not null default '{}', -- retailer -> open native cart id
  updated_at   timestamptz not null default now()
);

create table if not exists user_orders (
  id         text primary key,          -- the consolidated TATA-… order id
  user_id    uuid not null references auth.users (id) on delete cascade,
  payload    jsonb not null,            -- the full UCP order_confirmation
  created_at timestamptz not null default now()
);
create index if not exists user_orders_user_idx on user_orders (user_id, created_at desc);

-- global cache of every item any search returned, so cart ops can resolve
-- item ids across restarts without re-querying retailers
create table if not exists catalog_cache (
  item_id    text primary key,
  item       jsonb not null,            -- the UCP-shaped item
  updated_at timestamptz not null default now()
);

-- connector registry: one row per attached backend API -------------------------
-- Attaching a new API (digieca, ashiyana, ...) = one adapter class in
-- wrapper/adapters/ + one row here. Secrets never live in this table: `auth`
-- holds {"header": "X-Api-Key", "env": "DIGIECA_KEY"} and the value comes
-- from the named environment variable at runtime.
create table if not exists connectors (
  name         text primary key,
  adapter_path text not null,           -- dotted path, e.g. 'wrapper.adapters.croma:CromaAdapter'
  base_url     text not null,
  auth         jsonb not null default '{}',
  description  text not null,           -- used verbatim in the LLM routing prompt
  enabled      boolean not null default true
);

-- row-level security ------------------------------------------------------------
alter table bigbasket_products enable row level security;
alter table bigbasket_carts    enable row level security;
alter table bigbasket_orders   enable row level security;
alter table croma_products     enable row level security;
alter table croma_carts        enable row level security;
alter table croma_orders       enable row level security;
alter table user_carts         enable row level security;
alter table user_orders        enable row level security;
alter table catalog_cache      enable row level security;
alter table connectors         enable row level security;

-- catalogs are public; everything else is service-role only (no policies)
drop policy if exists "catalog is public" on bigbasket_products;
create policy "catalog is public" on bigbasket_products
  for select to anon, authenticated using (true);
drop policy if exists "catalog is public" on croma_products;
create policy "catalog is public" on croma_products
  for select to anon, authenticated using (true);
