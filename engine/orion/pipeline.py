"""ORION command line.

    python -m orion.pipeline seed                 # instruments + data source registry
    python -m orion.pipeline daily [--full] [--no-trade] [--dry-run]
    python -m orion.pipeline backtest
    python -m orion.pipeline doctor               # check every data source is reachable
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from dataclasses import asdict

import numpy as np
import pandas as pd

from . import config
from .analysis.research import scenarios, thesis, what_changed
from .backtest.walkforward import walk_forward
from .db import DB
from .features.core import atr as atr_fn
from .features.core import build_panel
from .ingestion import macro as macro_src
from .ingestion.oanda import fetch_all_prices
from .ingestion.validation import validate_prices, validate_series
from .regimes.engine import analogues, classify
from .signals.engine import compute_all, decompose, label


def _redact(text: str) -> str:
    """pipeline_runs is a public table and Actions logs may be public: strip secrets / account ids."""
    import os
    for k in ("OANDA_ACCOUNT_ID", "OANDA_API_TOKEN", "SUPABASE_SERVICE_ROLE_KEY", "FRED_API_KEY", "EIA_API_KEY"):
        v = os.environ.get(k)
        if v:
            text = text.replace(v, f"<{k}>")
    return text


class Run:
    def __init__(self, db: DB, kind: str):
        self.db, self.kind, self.steps, self.t0 = db, kind, [], time.time()
        self.row = db.insert_returning("pipeline_runs", {"kind": kind, "status": "running"})

    def step(self, name: str, status: str = "ok", detail=None):
        self.steps.append({"step": name, "status": status, "t": round(time.time() - self.t0, 1), "detail": detail})
        print(f"[{self.kind}] {name}: {status}" + (f" {detail}" if detail and status != "ok" else ""), flush=True)

    def finish(self, status: str, freshness=None):
        if "id" in self.row:
            self.db.update("pipeline_runs", {"id": self.row["id"]},
                           {"status": status, "finished_at": pd.Timestamp.now(tz="UTC").isoformat(),
                            "steps": self.steps, "freshness": freshness})


# ---------------------------------------------------------------------------
def load_data(run: Run | None = None):
    prices = fetch_all_prices(list(config.INSTRUMENTS), config.START_DATE)
    macro = macro_src.fetch_all_macro(config.START_DATE)
    issues = []
    for s, df in prices.items():
        issues += [i.dict() for i in validate_prices(s, df)]
    for sid, s in macro.items():
        issues += [i.dict() for i in validate_series(sid, s, config.SERIES[sid].frequency)]
    if run:
        run.step("validate", "warn" if issues else "ok", issues)
    errors = [i for i in issues if i["level"] == "error"]
    if errors:
        raise RuntimeError(f"validation errors: {errors}")
    return prices, macro, issues


def compute(prices, macro):
    panel, aligned = build_panel(prices, macro)
    frames = compute_all(panel, aligned)
    regime = classify(panel, aligned)
    return panel, aligned, frames, regime


def freshness(prices, macro) -> dict:
    out = {s: str(df.index[-1].date()) for s, df in prices.items()}
    out.update({s: str(v.index[-1].date()) for s, v in macro.items()})
    return out


# ---------------------------------------------------------------------------
def cmd_seed(db: DB):
    db.upsert("instruments", [{"symbol": i.symbol, "name": i.name, "asset_class": i.asset_class, "base_ccy": i.base,
                               "quote_ccy": i.quote, "themes": list(i.themes)} for i in config.INSTRUMENTS.values()],
              on_conflict="symbol")
    rows = [{"id": s.id, "name": s.name, "provider": s.provider, "url": s.url, "frequency": s.frequency, "units": s.units,
             "release_lag": f"{s.lag_days} calendar days", "license": s.license, "notes": s.notes}
            for s in config.SERIES.values()]
    rows.append({"id": "OANDA_PRICES", "name": "FX and commodity CFD mid prices (daily, 17:00 New York)", "provider": "oanda",
                 "url": "https://developer.oanda.com/rest-live-v20/instrument-ep/", "frequency": "daily", "units": "price",
                 "release_lag": "available at the 17:00 NY close", "license":
                 "OANDA practice account data, personal use. Raw levels are kept admin-only; public pages show derived analytics.",
                 "notes": "Also the execution venue for the paper portfolio."})
    db.upsert("data_sources", rows, on_conflict="id")
    print("seeded instruments and data_sources")


def cmd_daily(db: DB, full: bool, trade: bool, dry_run: bool):
    run = Run(db, "daily")
    try:
        prices, macro, _ = load_data(run)
        run.step("ingest", detail={"prices": len(prices), "macro": len(macro)})
        panel, aligned, frames, regime = compute(prices, macro)
        asof = min(df.index[-1] for df in prices.values())
        run.step("signals", detail={"asof": str(asof.date())})

        since = panel.index[0] if full else asof - pd.Timedelta(days=45)
        # raw prices (admin-only table) and public rebased index
        prow, irow = [], []
        for s, df in prices.items():
            d = df.loc[since:]
            base = float(df["close"].iloc[0])
            for dt_, r in d.iterrows():
                prow.append({"symbol": s, "date": dt_.date(), "open": r["open"], "high": r["high"], "low": r["low"],
                             "close": r["close"], "source": "oanda"})
                irow.append({"symbol": s, "date": dt_.date(), "index_value": r["close"] / base * 100})
        db.upsert("prices_daily", prow, on_conflict="symbol,date")
        db.upsert("market_index_public", irow, on_conflict="symbol,date")

        mrow = []
        for sid, s in macro.items():
            lag = config.SERIES[sid].lag_days
            for dt_, v in s.loc[since - pd.Timedelta(days=120):].items():
                mrow.append({"series_id": sid, "date": dt_.date(), "available_on": (dt_ + pd.Timedelta(days=lag)).date(),
                             "value": v, "source": config.SERIES[sid].provider})
        db.upsert("macro_series", mrow, on_conflict="series_id,date")

        srow = []
        for sym, f in frames.items():
            for dt_, r in f.loc[since:].iterrows():
                if pd.isna(r["composite"]):
                    continue
                srow.append({"date": dt_.date(), "symbol": sym, "composite": r["composite"], "label": label(r["composite"]),
                             "components": decompose(sym, r), "completeness": r["completeness"]})
        db.upsert("signals", srow, on_conflict="date,symbol")

        rrow = []
        for dt_, r in regime.loc[since:].iterrows():
            rrow.append({"date": dt_.date(), "growth": r["growth"], "inflation": r["inflation"], "risk": r["risk"],
                         "usd": r["usd"], "volatility": r["volatility"], "label": r["label"],
                         "inputs": {k: r.get(f"{k}_x") for k in ("growth", "inflation", "risk", "usd", "volatility")}})
        db.upsert("regimes", rrow, on_conflict="date")
        run.step("store")

        params = config.StrategyParams()
        theses = {s: thesis(s, frames[s], aligned[s], regime.loc[asof], asof,
                            float(atr_fn(aligned[s]).loc[asof]), params.stop_atr_multiple) for s in frames}
        snap = {"date": asof.date(), "what_changed": what_changed(panel, aligned, frames, asof),
                "analogues": analogues(regime, aligned, asof), "theses": theses,
                "scenarios": scenarios(panel, aligned, asof)}
        db.upsert("market_snapshots", [snap], on_conflict="date")
        run.step("research")

        if trade:
            from .agent.trader import run as agent_run
            res = agent_run(frames, aligned, regime, asof, db, force_dry_run=dry_run)
            run.step("agent", detail=res)
        run.finish("success", freshness(prices, macro))
    except Exception as e:  # noqa: BLE001
        run.step("error", "error", _redact(f"{type(e).__name__}: {str(e)[:300]}"))
        run.finish("failed")
        print(_redact(traceback.format_exc()), file=sys.stderr)
        sys.exit(1)


def cmd_backtest(db: DB):
    run = Run(db, "backtest")
    try:
        prices, macro, _ = load_data(run)
        panel, aligned, frames, _ = compute(prices, macro)
        res = walk_forward(aligned, frames, panel)
        run.step("walk_forward")
        for old in db.select("backtest_runs", {"select": "id", "is_latest": "eq.true"}):
            db.update("backtest_runs", {"id": old["id"]}, {"is_latest": False})
        row = db.insert_returning("backtest_runs", {
            "name": "Composite signal, walk-forward", "is_latest": True, "config": res["config"],
            "metrics_in_sample": res["metrics_in_sample"], "metrics_out_of_sample": res["metrics_out_of_sample"],
            "metrics_holdout": res["metrics_holdout"], "walk_forward": res["walk_forward"],
            "diagnostics": res["diagnostics"], "per_instrument": res["per_instrument"]})
        rid = row.get("id", "local")
        ser = res["series"]
        db.upsert("backtest_series", [{"run_id": rid, "date": r.date.date(), "segment": r.segment, "equity": r.equity,
                                       "drawdown": r.drawdown} for r in ser.itertuples()], on_conflict="run_id,segment,date")
        tr = res["trades"]
        # Trade prices are omitted from the public table (see licensing note); returns are kept.
        db.upsert("backtest_trades", [{"run_id": rid, "segment": t.segment, "symbol": t.symbol, "direction": int(t.direction),
                                       "entry_date": t.entry_date, "exit_date": t.exit_date, "weight": t.weight,
                                       "return_pct": t.return_pct, "bars": int(t.bars), "exit_reason": t.exit_reason}
                                      for t in tr.itertuples()])
        run.step("store", detail={"run_id": rid, "oos_sharpe": res["metrics_out_of_sample"].get("sharpe")})
        run.finish("success", freshness(prices, macro))
    except Exception as e:  # noqa: BLE001
        run.step("error", "error", _redact(f"{type(e).__name__}: {str(e)[:300]}"))
        run.finish("failed")
        print(_redact(traceback.format_exc()), file=sys.stderr)
        sys.exit(1)


def cmd_smoketest(db: DB) -> int:
    """End-to-end check with the smallest possible trade: 1 unit of EUR/USD (~$1 notional) on the
    PRACTICE account. Opens it with a stop attached, confirms the position, closes it, confirms flat,
    and checks Supabase writes. Logs never show NAV or balances (Actions logs may be public)."""
    import time as _t
    from .ingestion.oanda import Oanda
    sym, units = "EUR_USD", 1
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
        return ok

    try:
        o = Oanda()
        acct = o.summary()
        check("connected to OANDA practice API", True)
        check("account currency is USD", acct.get("currency") == "USD", f"got {acct.get('currency')}")
        existing = o.open_positions().get(sym, {}).get("units", 0)
        if not check(f"no existing {sym} position (so the test cannot disturb the agent)", existing == 0,
                     "skip: close it first" if existing else ""):
            raise SystemExit(1)
        q = o.prices([sym]).get(sym)
        if not check("live price received", q and q["tradeable"], "market closed? try on a weekday" if q and not q["tradeable"] else ""):
            raise SystemExit(1)
        stop = f"{q['mid'] * 0.98:.5f}"   # 2% below: only there to prove stop-on-fill works
        resp = o.market_order(sym, units, stop, "orion smoketest")
        fill = resp.get("orderFillTransaction")
        check("1-unit market order filled", fill is not None, (resp.get("orderCancelTransaction") or {}).get("reason", ""))
        _t.sleep(2)
        pos = o.open_positions().get(sym, {})
        check("position visible with 1 unit", pos.get("units") == units, f"units={pos.get('units')}")
        trades = [t for t in o.open_trades() if t["instrument"] == sym]
        check("stop-loss attached to the trade", any(t.get("stopLossOrder") for t in trades))
        o.close_position(sym, units)
        _t.sleep(2)
        check("position closed, account flat in EUR_USD", o.open_positions().get(sym, {}).get("units", 0) == 0)
    except SystemExit:
        pass
    except Exception as e:  # noqa: BLE001
        check("OANDA round trip", False, _redact(f"{type(e).__name__}: {str(e)[:200]}"))

    if not db.local:
        try:
            row = db.insert_returning("pipeline_runs", {"kind": "smoketest", "status": "running"})
            db.update("pipeline_runs", {"id": row["id"]}, {"status": "success", "finished_at": pd.Timestamp.now(tz="UTC").isoformat(),
                                                        "steps": [{"step": n, "status": "ok" if ok else "fail"} for n, ok, _ in checks]})
            check("Supabase write with service key", True)
            cfg = db.select("agent_config", {"select": "trading_enabled", "id": "eq.1"})
            check("agent_config readable (migration applied)", len(cfg) == 1,
                  f"trading_enabled={cfg[0]['trading_enabled']}" if cfg else "run the SQL migration")
        except Exception as e:  # noqa: BLE001
            check("Supabase write with service key", False, _redact(str(e)[:200]))
    else:
        print("SKIP  Supabase checks (SUPABASE_URL not set)")
    failed = [n for n, ok, _ in checks if not ok]
    print("\nSMOKE TEST " + ("PASSED" if not failed else f"FAILED: {', '.join(failed)}"))
    return 0 if not failed else 1


def cmd_doctor():
    ok = True
    for sid, spec in config.SERIES.items():
        try:
            s = macro_src.fetch_series(spec, "2024-01-01")
            print(f"OK    {sid:<16} {len(s):>5} obs, last {s.index[-1].date()} = {s.iloc[-1]}")
        except Exception as e:  # noqa: BLE001
            print(f"{'SKIP' if spec.optional else 'FAIL'}  {sid:<16} {e}")
            ok = ok and spec.optional
    try:
        from .ingestion.oanda import Oanda
        o = Oanda()
        df = o.candles_daily("EUR_USD", "2025-01-01")
        acct = o.summary()
        print(f"OK    OANDA candles {len(df)} bars; account currency {acct['currency']}, NAV {acct['NAV']}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  OANDA {e}")
        ok = False
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="orion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    d = sub.add_parser("daily")
    d.add_argument("--full", action="store_true", help="write full history, not just the last 45 days")
    d.add_argument("--no-trade", action="store_true", help="skip the paper-trading agent")
    d.add_argument("--dry-run", action="store_true", help="agent computes and logs orders but does not send them")
    sub.add_parser("backtest")
    sub.add_parser("doctor")
    sub.add_parser("smoketest", help="1-unit EUR/USD round trip on the practice account")
    a = ap.parse_args(argv)
    if a.cmd == "doctor":
        return cmd_doctor()
    db = DB()
    if db.local:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: writing to " + str(db.out) + "/*.jsonl")
    if a.cmd == "seed":
        cmd_seed(db)
    elif a.cmd == "daily":
        cmd_daily(db, a.full, not a.no_trade, a.dry_run)
    elif a.cmd == "backtest":
        cmd_backtest(db)
    elif a.cmd == "smoketest":
        return cmd_smoketest(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
