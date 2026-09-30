-- ORION schema
-- Two tiers of data:
--   PUBLIC  research tables  -> readable by anyone (anon + authenticated), written only by the pipeline (service role)
--   PRIVATE portfolio tables -> readable only by users listed in public.admins, written only by the pipeline
-- The service_role key bypasses RLS and must only ever live in GitHub Actions secrets, never in the web app.

-- gen_random_uuid() is built into Postgres 13+

-- ---------------------------------------------------------------------------
-- Admin registry + helper
-- ---------------------------------------------------------------------------
create table if not exists public.admins (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.admins a where a.user_id = auth.uid());
$$;

revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to anon, authenticated;

-- ---------------------------------------------------------------------------
-- PUBLIC research tables
-- ---------------------------------------------------------------------------
create table if not exists public.instruments (
  symbol text primary key,             -- e.g. USD_JPY (OANDA naming)
  name text not null,
  asset_class text not null check (asset_class in ('fx','commodity')),
  base_ccy text not null,
  quote_ccy text not null,
  themes text[] not null default '{}'
);

create table if not exists public.prices_daily (
  symbol text not null references public.instruments(symbol),
  date date not null,                  -- NY 17:00 close date
  open double precision, high double precision, low double precision, close double precision not null,
  source text not null,
  primary key (symbol, date)
);

-- Public, derived view of each market: price rebased to 100 at the first observation.
-- Raw OANDA prices stay admin-only (see docs/DATA_SOURCES.md: OANDA data is licensed for personal use).
create table if not exists public.market_index_public (
  symbol text not null references public.instruments(symbol),
  date date not null,
  index_value double precision not null,
  primary key (symbol, date)
);

create table if not exists public.macro_series (
  series_id text not null,
  date date not null,                  -- observation date
  available_on date not null,          -- first date the value could be used (release-lag adjusted)
  value double precision not null,
  source text not null,
  primary key (series_id, date)
);

create table if not exists public.data_sources (
  id text primary key,
  name text not null,
  provider text not null,
  url text not null,
  frequency text not null,
  units text,
  release_lag text,
  license text not null,
  notes text
);

create table if not exists public.signals (
  date date not null,
  symbol text not null references public.instruments(symbol),
  composite double precision,
  label text,                           -- Positive / Neutral / Negative
  components jsonb not null,            -- {name: {value, weight, contribution, raw, description}}
  completeness double precision,        -- share of component weight with data
  primary key (date, symbol)
);

create table if not exists public.regimes (
  date date primary key,
  growth text, inflation text, risk text, usd text, volatility text,
  label text not null,
  inputs jsonb not null
);

create table if not exists public.market_snapshots (
  -- one row per date; payloads for the overview page (what changed, analogues, theses, scenarios)
  date date primary key,
  what_changed jsonb,
  analogues jsonb,
  theses jsonb,
  scenarios jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.backtest_runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  name text not null,
  is_latest boolean not null default false,
  config jsonb not null,
  metrics_in_sample jsonb,
  metrics_out_of_sample jsonb,
  metrics_holdout jsonb,
  walk_forward jsonb,
  diagnostics jsonb,
  per_instrument jsonb
);

create table if not exists public.backtest_series (
  run_id uuid not null references public.backtest_runs(id) on delete cascade,
  date date not null,
  segment text not null check (segment in ('in_sample','out_of_sample','holdout')),
  equity double precision not null,
  drawdown double precision not null,
  primary key (run_id, segment, date)
);

create table if not exists public.backtest_trades (
  id bigserial primary key,
  run_id uuid not null references public.backtest_runs(id) on delete cascade,
  segment text not null,
  symbol text not null,
  direction smallint not null,
  entry_date date not null, exit_date date,
  entry_price double precision, exit_price double precision,
  weight double precision,
  return_pct double precision,
  bars integer,
  exit_reason text
);

create table if not exists public.pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  kind text not null default 'daily',
  steps jsonb not null default '[]'::jsonb,
  freshness jsonb
);

-- Public strategy performance: % index and drawdown only. No sizes, no currency amounts, no positions.
create table if not exists public.performance_public (
  date date primary key,
  nav_index double precision not null,  -- 100 = inception
  drawdown double precision not null     -- fraction, <= 0
);

-- ---------------------------------------------------------------------------
-- PRIVATE portfolio tables (admin only)
-- ---------------------------------------------------------------------------
create table if not exists public.agent_config (
  id smallint primary key default 1 check (id = 1),
  trading_enabled boolean not null default false,   -- kill switch, off until you turn it on
  risk_per_trade double precision not null default 0.005,
  stop_atr_multiple double precision not null default 2.5,
  entry_threshold double precision not null default 0.5,
  exit_threshold double precision not null default 0.0,
  max_gross_leverage double precision not null default 3.0,
  max_position_weight double precision not null default 1.0,
  max_currency_exposure double precision not null default 1.5,
  halt_drawdown double precision not null default 0.15,
  rebalance_band double precision not null default 0.25,
  halted_reason text,
  updated_at timestamptz not null default now(),
  updated_by uuid
);
insert into public.agent_config (id) values (1) on conflict do nothing;

create table if not exists public.equity_snapshots (
  date date primary key,
  nav double precision not null,
  balance double precision,
  unrealized_pl double precision,
  margin_used double precision,
  gross_exposure double precision,
  currency_exposure jsonb,
  portfolio_vol double precision,
  drawdown double precision,
  risk jsonb
);

create table if not exists public.positions_snapshot (
  date date not null,
  symbol text not null,
  units double precision not null,
  avg_price double precision,
  unrealized_pl double precision,
  notional_usd double precision,
  weight double precision,
  stop_price double precision,
  primary key (date, symbol)
);

create table if not exists public.orders (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  date date not null,
  symbol text not null,
  units double precision not null,
  intent text not null,               -- open / close / resize / flatten
  status text not null,               -- dry_run / filled / rejected / error
  broker_order_id text,
  fill_price double precision,
  stop_price double precision,
  response jsonb,
  error text
);

create table if not exists public.journal (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  date date not null,
  symbol text,
  action text not null,               -- enter_long / enter_short / exit / hold / resize / halt / skip
  summary text not null,
  detail jsonb not null default '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'instruments','market_index_public','macro_series','data_sources','signals','regimes',
    'market_snapshots','backtest_runs','backtest_series','backtest_trades','pipeline_runs','performance_public'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "public read" on public.%I', t);
    execute format('create policy "public read" on public.%I for select to anon, authenticated using (true)', t);
    execute format('revoke insert, update, delete, truncate on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to anon, authenticated', t);
  end loop;

  foreach t in array array['prices_daily','agent_config','equity_snapshots','positions_snapshot','orders','journal'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('revoke insert, update, delete, truncate on public.%I from authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format('drop policy if exists "admin read" on public.%I', t);
    execute format('create policy "admin read" on public.%I for select to authenticated using ((select public.is_admin()))', t);
  end loop;
end $$;

-- Admins may change agent settings (kill switch, risk limits) but nothing else.
grant update (trading_enabled, risk_per_trade, stop_atr_multiple, entry_threshold, exit_threshold,
              max_gross_leverage, max_position_weight, max_currency_exposure, halt_drawdown,
              rebalance_band, halted_reason, updated_at, updated_by)
  on public.agent_config to authenticated;
drop policy if exists "admin update" on public.agent_config;
create policy "admin update" on public.agent_config for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- Sanity bounds so a typo in the admin UI cannot set dangerous limits.
alter table public.agent_config drop constraint if exists agent_config_bounds;
alter table public.agent_config add constraint agent_config_bounds check (
  risk_per_trade between 0 and 0.02
  and stop_atr_multiple between 0.5 and 10
  and entry_threshold between 0 and 3
  and exit_threshold between -1 and 3
  and max_gross_leverage between 0 and 10
  and max_position_weight between 0 and 5
  and max_currency_exposure between 0 and 10
  and halt_drawdown between 0.01 and 0.5
  and rebalance_band between 0 and 1
);

alter table public.admins enable row level security;
revoke all on public.admins from anon;
revoke insert, update, delete, truncate on public.admins from authenticated;
grant select on public.admins to authenticated;
drop policy if exists "see own admin row" on public.admins;
create policy "see own admin row" on public.admins for select to authenticated using (user_id = (select auth.uid()));

-- Helpful indexes
create index if not exists signals_symbol_date on public.signals(symbol, date desc);
create index if not exists prices_symbol_date on public.prices_daily(symbol, date desc);
create index if not exists journal_date on public.journal(date desc);
create index if not exists orders_date on public.orders(date desc);
