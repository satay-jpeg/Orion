# ORION: Cross-Asset Macro Trading Intelligence

An explainable research platform that connects macro conditions to FX and commodity signals, tests them with walk-forward backtests, and runs the same rule in a paper-trading account with portfolio-level risk limits.

> Not "an AI that predicts forex prices". Every signal breaks down into named inputs, every trade has an invalidation level, and the backtest is judged on out-of-sample data and an untouched holdout.

**Universe:** USD/JPY, EUR/USD, AUD/USD, USD/CAD, gold, Brent, copper.

## What it does

| Layer | What happens | Where |
|---|---|---|
| Data | OANDA daily candles; rates, inflation, activity, VIX and USD index from official free sources, each stored with a release-lag-adjusted `available_on` date | `engine/orion/ingestion` |
| Signals | Rate-differential impulse, carry, risk sentiment, cross-asset and trend components as clipped z-scores, combined with equal weights | `engine/orion/signals` |
| Regime | Growth / inflation / risk / USD / volatility, one documented rule each, plus historical analogues | `engine/orion/regimes` |
| Research | "What changed?", template-based theses with catalysts, risks and invalidation, and scenario shocks | `engine/orion/analysis` |
| Backtest | Next-day execution, ATR stops, risk-based sizing, spreads, slippage and financing; yearly walk-forward plus a 12-month holdout; component IC report | `engine/orion/backtest` |
| Risk | Position sizing, currency-leg exposure, correlation-aware portfolio vol, risk contributions | `engine/orion/risk` |
| Agent | Applies the backtested rule each day after the NY close, enforces limits, trades the OANDA **practice** account, journals every decision | `engine/orion/agent` |
| Web | Next.js dashboard: public research pages plus a private `/admin` book | `web/` |

## Architecture

```
GitHub Actions (cron, 07:20 SGT Mon-Fri)
  └─ python -m orion.pipeline daily
       ├─ fetch  : OANDA v20 · FRED · MoF Japan · ECB · RBA · Bank of Canada · EIA
       ├─ build  : point-in-time panel → signals → regime → research payloads
       ├─ agent  : targets → limits → OANDA practice orders → journal + snapshots
       └─ write  : Supabase (service-role key, server side only)

Supabase Postgres + RLS
  ├─ public tables  : signals, regimes, snapshots, backtests, rebased index, % performance
  └─ private tables : prices, positions, orders, journal, NAV, agent settings  (admins only)

Vercel (Next.js)
  ├─ public pages   : anon key, read-only, cached 10 min
  └─ /admin         : Supabase Auth session + is_admin() check; RLS enforces it again in the DB
```

## Security model

* **Two tiers enforced in the database.** Row Level Security lets everyone read only the public research tables. Portfolio tables need `public.is_admin()`, which checks `auth.uid()` against the `admins` table. Nobody can write through the API except the pipeline's service role.
* **No public sign-up.** Turn off sign-ups in Supabase. Even if someone creates an account, they are not in `admins` and see nothing private. This is tested in `supabase/tests/rls_check.py`.
* **What the public sees about the portfolio:** only an index (100 = start) and drawdown, from a separate `performance_public` table. Pipeline logs and the public `pipeline_runs` table never contain NAV, sizes or account IDs.
* **Admins can change only the agent settings.** They are limited by column-level grants and database CHECK bounds: risk per trade is capped at 2%, and so on.
* **Hardening:** CSP and security headers, `/admin` served `no-store`, and `getUser()` (server-verified) rather than a cookie-only session check. The service-role key exists only in GitHub Actions secrets. The OANDA client refuses anything other than the practice environment.

## Quick start

See **[docs/SETUP.md](docs/SETUP.md)** for step-by-step setup with accounts (about 30 minutes).

```bash
# engine
cd engine && pip install -r requirements.txt && python -m pytest -q
python -m orion.pipeline doctor      # checks every data source + OANDA
python -m orion.pipeline seed
python -m orion.pipeline daily --full --dry-run
python -m orion.pipeline backtest

# web
cd web && cp .env.example .env.local && npm install && npm run dev
```

Without Supabase credentials the engine writes JSONL files to `./out/`, which is handy for development.

## Documentation

* [docs/METHODOLOGY.md](docs/METHODOLOGY.md): signal design, look-ahead controls, backtest assumptions, limitations
* [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md): every dataset with frequency, lag and licence
* [docs/SETUP.md](docs/SETUP.md): accounts, secrets and deployment
* [docs/INTERVIEW_NOTES.md](docs/INTERVIEW_NOTES.md): talking points

## Design notes

The UI is a flat, dark "desk tool": hairline rules instead of cards and shadows, monospaced tabular figures, a single blue accent, and a diverging blue/red scale for signals. It has no gradients. Three small components take their idea from patterns in the [componentry.dev](https://componentry.dev/) catalogue: a split-flap regime label, a calendar-style monthly-returns grid, and status-card instrument tiles. All three are written from scratch in plain CSS/SVG, with no code copied. Fonts are IBM Plex Sans/Mono (SIL Open Font License), self-hosted through `@fontsource`.

## Disclaimer

Research and paper trading only. Nothing here is investment advice.
