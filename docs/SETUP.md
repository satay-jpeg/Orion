# Setup guide

Allow about 30–45 minutes. Everything below is free-tier.

## 0. Accounts you need

| Service | Purpose | Cost |
|---|---|---|
| GitHub | Code and the scheduled pipeline (GitHub Actions) | Free |
| Supabase | Postgres, Auth, Row Level Security | Free tier |
| Vercel | Hosts the website | Hobby tier (you already have this) |
| OANDA demo (practice) | Market data and paper execution | Free |
| FRED API key | Optional, more reliable than the keyless CSV endpoint | Free |
| EIA API key | Optional, enables the oil curve and inventory components | Free |

## 1. GitHub

1. Create a repository named `orion` and push this folder to it.
2. A public repo is fine and helps with employers: secrets stay in GitHub Secrets, and the pipeline never prints NAV, sizes or account IDs.
3. Note: GitHub pauses scheduled workflows in public repos after 60 days without commits. Push something occasionally, or re-enable the workflow from the Actions tab.

## 2. Supabase

1. Create a project. Pick the region closest to you (Singapore, `ap-southeast-1`).
2. **SQL Editor → New query**: paste all of `supabase/migrations/0001_init.sql` and run it. It is safe to run again.
3. **Authentication → Sign In / Providers → Email**: turn **off** "Allow new users to sign up".
4. **Authentication → Users → Add user**: create your own login (email + strong password, tick auto-confirm).
5. Make yourself admin (SQL Editor):
   ```sql
   insert into public.admins (user_id)
   select id from auth.users where email = 'you@example.com';
   ```
6. Recommended: **Authentication → Multi-Factor** enable TOTP for your account.
7. **Project Settings → API**: copy the Project URL, the `anon` public key and the `service_role` key. The service_role key goes **only** into GitHub Secrets (step 5), never into Vercel.

## 3. OANDA practice account

1. Sign up for a demo account on OANDA's site for your region. Choose **USD** as the account currency; the agent refuses other currencies.
2. Generate a personal API token (Account → *Manage API Access*).
3. Note the v20 account ID (format `101-003-XXXXXXX-001`).
4. Instrument availability differs by OANDA division. The pipeline skips any of `XAU_USD`, `BCO_USD`, `XCU_USD` your division does not offer and logs it. The `doctor` command shows what is available.

## 4. Optional keys

* FRED: https://fred.stlouisfed.org/docs/api/api_key.html
* EIA: https://www.eia.gov/opendata/register.php. Without it the Brent curve/inventory components are skipped and the composite renormalises over the rest.

## 5. GitHub Secrets

Repo → Settings → Secrets and variables → Actions → *New repository secret*:

| Name | Value |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role key |
| `OANDA_API_TOKEN` | OANDA practice token |
| `OANDA_ACCOUNT_ID` | e.g. `101-003-1234567-001` |
| `FRED_API_KEY` | optional |
| `EIA_API_KEY` | optional |

## 6. First runs (Actions tab)

1. **ORION one-off setup / diagnostics** → `doctor`. Every required source should say OK.
2. Same workflow → `seed` (instruments + data-source registry).
3. **ORION daily pipeline** → mode `full` (writes full history; the agent runs in dry-run because trading is off by default).
4. **ORION weekly walk-forward backtest** → run once (about 5–10 minutes).
5. **ORION one-off setup / diagnostics** → `smoketest` (weekdays, market open). It buys 1 unit of EUR/USD
   (about $1 of exposure) on the practice account with a stop attached, confirms the position, closes it, confirms the
   account is flat, and checks Supabase writes. Every line should say PASS.

## 7. Website on Vercel

1. *Add New → Project* → import the repo → **Root Directory: `web`**.
2. Environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
3. Deploy. Public pages refresh every 10 minutes. Sign in at `/login` and your book is at `/admin`.
4. Supabase → Authentication → URL Configuration: set Site URL to your Vercel domain.

## 8. Turn the agent on

Watch a few dry-run days in `/admin` (journal and orders show `dry_run`). When you are happy, tick **Trading enabled** in *Agent settings*. From the next run the agent sends orders to the practice account. The circuit breaker switches trading off automatically if drawdown passes the limit.

## Schedule

| Workflow | When (SGT) | What |
|---|---|---|
| daily | 07:20 Mon–Fri | ingest → signals → regime → research → agent → snapshots |
| backtest | Sat 10:40 | walk-forward + holdout, replaces the "latest" run |
| CI | every push | engine tests + web build |

## Local development

```bash
cd engine && pip install -r requirements.txt && python -m pytest -q
cd supabase/tests && pip install pgserver psycopg2-binary && python rls_check.py   # RLS check on a throwaway Postgres
cd web && cp .env.example .env.local && npm install && npm run dev
```
