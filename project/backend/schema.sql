-- GulfDeals — Supabase PostgreSQL Schema
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- ─── EXTENSIONS ──────────────────────────────────────────────────────────────
create extension if not exists "uuid-ossp";
create extension if not exists "pg_cron";          -- for scheduled jobs

-- ─── PRODUCTS ─────────────────────────────────────────────────────────────────
create table if not exists products (
  id              uuid primary key default uuid_generate_v4(),
  category        text not null check (category in ('laptop','cpu','gpu','ram','ssd','monitor')),
  brand           text not null,
  model           text not null,
  retailer        text not null check (retailer in ('amazon_ae','noon','sharaf_dg','emax','virgin')),
  retailer_id     text,                             -- retailer's own product/ASIN id
  product_url     text not null,
  affiliate_url   text,
  image_url       text,
  current_price   numeric(10,2) not null,
  original_price  numeric(10,2),
  discount_pct    numeric(5,2) generated always as (
                    case when original_price > 0
                    then round(((original_price - current_price) / original_price) * 100, 2)
                    else 0 end
                  ) stored,
  specs           jsonb default '{}',              -- flexible: {screen, cpu, gpu, ram, ...}
  tags            text[] default '{}',
  is_available    boolean default true,
  is_hot          boolean default false,
  rating          numeric(3,1),
  review_count    int default 0,
  last_scraped    timestamptz,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now(),

  unique (retailer, retailer_id)                   -- prevent duplicate listings
);

-- Auto-update updated_at
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger products_updated_at
  before update on products
  for each row execute function update_updated_at();

-- Auto-compute is_hot
create or replace function refresh_is_hot()
returns trigger language plpgsql as $$
begin
  new.is_hot := (new.discount_pct >= 20 and coalesce(new.rating, 0) >= 4.3 and new.is_available);
  return new;
end;
$$;

create trigger products_is_hot
  before insert or update on products
  for each row execute function refresh_is_hot();

-- ─── PRICE HISTORY ────────────────────────────────────────────────────────────
create table if not exists price_history (
  id          bigserial primary key,
  product_id  uuid not null references products(id) on delete cascade,
  price       numeric(10,2) not null,
  retailer    text not null,
  scraped_at  timestamptz default now()
);

create index idx_price_history_product_time on price_history(product_id, scraped_at desc);

-- Only insert if price actually changed (avoid duplicate rows)
create or replace function insert_price_if_changed()
returns trigger language plpgsql as $$
declare
  last_price numeric;
begin
  select price into last_price
  from price_history
  where product_id = new.id
  order by scraped_at desc
  limit 1;

  if last_price is distinct from new.current_price then
    insert into price_history(product_id, price, retailer)
    values (new.id, new.current_price, new.retailer);
  end if;
  return new;
end;
$$;

create trigger products_price_history
  after insert or update of current_price on products
  for each row execute function insert_price_if_changed();

-- ─── ALERTS (user subscriptions) ─────────────────────────────────────────────
create table if not exists alerts (
  id            uuid primary key default uuid_generate_v4(),
  product_id    uuid references products(id) on delete cascade,  -- null = "any new deal"
  channel       text not null check (channel in ('email','whatsapp')),
  destination   text not null,                    -- email or E.164 phone e.g. +971501234567
  target_price  numeric(10,2),                    -- notify when price ≤ this
  alert_type    text not null default 'price_drop'
                  check (alert_type in ('price_drop','any_change','new_deal')),
  active        boolean default true,
  token         uuid default uuid_generate_v4(),  -- unsubscribe token (in email footer)
  created_at    timestamptz default now()
);

create index idx_alerts_product on alerts(product_id) where active = true;
create index idx_alerts_destination on alerts(destination);

-- ─── ALERT EVENTS (audit log) ────────────────────────────────────────────────
create table if not exists alert_events (
  id          bigserial primary key,
  alert_id    uuid not null references alerts(id) on delete cascade,
  product_id  uuid not null references products(id) on delete cascade,
  old_price   numeric(10,2),
  new_price   numeric(10,2) not null,
  channel     text not null,
  status      text not null check (status in ('sent','failed')),
  error_msg   text,
  sent_at     timestamptz default now()
);

-- ─── ROW LEVEL SECURITY ───────────────────────────────────────────────────────
-- Products and price_history: public read, service-role write only
alter table products      enable row level security;
alter table price_history enable row level security;
alter table alerts        enable row level security;
alter table alert_events  enable row level security;

create policy "Public can read products"
  on products for select using (true);

create policy "Public can read price_history"
  on price_history for select using (true);

create policy "Service role full access products"
  on products for all using (auth.role() = 'service_role');

create policy "Service role full access price_history"
  on price_history for all using (auth.role() = 'service_role');

create policy "Anyone can insert alert"
  on alerts for insert with check (true);

create policy "Service role manages alerts"
  on alerts for all using (auth.role() = 'service_role');

create policy "Service role manages alert_events"
  on alert_events for all using (auth.role() = 'service_role');

-- ─── HELPER VIEWS ─────────────────────────────────────────────────────────────
create or replace view deals_with_history as
select
  p.*,
  ph_min.price                         as price_7d_low,
  ph_max.price                         as price_7d_high,
  ph_first.price                       as price_30d_ago
from products p
left join lateral (
  select min(price) as price from price_history
  where product_id = p.id and scraped_at >= now() - interval '7 days'
) ph_min on true
left join lateral (
  select max(price) as price from price_history
  where product_id = p.id and scraped_at >= now() - interval '7 days'
) ph_max on true
left join lateral (
  select price from price_history
  where product_id = p.id and scraped_at >= now() - interval '30 days'
  order by scraped_at asc limit 1
) ph_first on true
where p.is_available = true;

-- ─── SCHEDULED CLEANUP (pg_cron) ─────────────────────────────────────────────
-- Purge price history older than 90 days (keeps DB lean)
select cron.schedule(
  'purge-old-price-history',
  '0 3 * * *',   -- 3am daily
  $$delete from price_history where scraped_at < now() - interval '90 days'$$
);

-- Mark products as unavailable if not scraped in 12h
select cron.schedule(
  'mark-stale-unavailable',
  '0 */6 * * *',
  $$update products set is_available = false
    where last_scraped < now() - interval '12 hours' and is_available = true$$
);
