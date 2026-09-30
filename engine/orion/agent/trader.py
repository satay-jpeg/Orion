"""The ORION paper-trading agent.

The agent does not "decide" anything a human cannot audit. Each run it:
  1. Reads the admin-controlled config (kill switch + risk limits) from Supabase.
  2. Checks the drawdown circuit breaker against the equity history.
  3. Converts today's composite signals into target positions with the SAME rule used in the backtest
     (hysteresis entry/exit, ATR stop, risk-based sizing), then applies portfolio limits
     (gross leverage, per-currency exposure).
  4. Reconciles targets with the OANDA practice account and sends market orders with stops attached.
  5. Writes orders, a journal entry with the full rationale, and equity/position snapshots.
If trading is disabled, steps 1-3 and 5 still run and orders are logged as 'dry_run'.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..analysis.research import thesis
from ..config import INSTRUMENTS
from ..db import DB
from ..features.core import atr as atr_fn
from ..ingestion.oanda import Oanda
from ..risk.portfolio import currency_exposure, notional_weights, portfolio_risk, position_size

DEFAULT_CFG = {"trading_enabled": False, "risk_per_trade": 0.005, "stop_atr_multiple": 2.5, "entry_threshold": 0.5,
               "exit_threshold": 0.0, "max_gross_leverage": 3.0, "max_position_weight": 1.0,
               "max_currency_exposure": 1.5, "halt_drawdown": 0.15, "rebalance_band": 0.25}


@dataclass
class Target:
    symbol: str
    direction: int
    units: float
    stop: float | None
    score: float
    reason: str


def desired_direction(current: int, score: float, entry: float, exit_: float) -> int:
    """Same hysteresis as the backtest: enter beyond +/-entry, hold until the score crosses exit."""
    if not np.isfinite(score):
        return current  # no new information -> do nothing
    if current > 0:
        if score <= -entry:
            return -1
        return 1 if score >= exit_ else 0
    if current < 0:
        if score >= entry:
            return 1
        return -1 if score <= -exit_ else 0
    return 1 if score >= entry else -1 if score <= -entry else 0


def _round_units(units: float, precision: int) -> float:
    f = 10 ** precision
    return math.floor(abs(units) * f) / f * (1 if units >= 0 else -1)


def build_targets(cfg: dict, nav: float, mids: dict[str, float], current: dict[str, float],
                  scores: dict[str, float], atrs: dict[str, float]) -> tuple[dict[str, Target], list[str]]:
    notes = []
    targets: dict[str, Target] = {}
    for sym, score in scores.items():
        cur_units = current.get(sym, 0.0)
        cur_dir = int(np.sign(cur_units))
        d = desired_direction(cur_dir, score, cfg["entry_threshold"], cfg["exit_threshold"])
        if d == 0 or not np.isfinite(atrs.get(sym, np.nan)):
            targets[sym] = Target(sym, 0, 0.0, None, score, "flat: signal inside band" if d == 0 else "flat: no ATR")
            continue
        mid = mids[sym]
        stop = mid - d * cfg["stop_atr_multiple"] * atrs[sym]
        sz = position_size(nav, cfg["risk_per_trade"], mid, stop, sym, mids)
        units = sz["units"]
        cap_units = cfg["max_position_weight"] * nav / (sz["notional_usd"] / units)
        if units > cap_units:
            notes.append(f"{sym}: size capped by max_position_weight")
            units = cap_units
        targets[sym] = Target(sym, d, d * units, stop, score, "signal")

    # Portfolio limits: gross leverage, then per-currency exposure
    w = notional_weights({s: t.units for s, t in targets.items()}, mids, nav)
    gross = sum(abs(x) for x in w.values())
    if gross > cfg["max_gross_leverage"] > 0:
        k = cfg["max_gross_leverage"] / gross
        notes.append(f"gross leverage {gross:.2f}x > limit; scaled by {k:.2f}")
        for t in targets.values():
            t.units *= k
    exp = currency_exposure({s: t.units for s, t in targets.items()}, mids)
    worst = max((abs(v) / nav for v in exp.values()), default=0)
    if worst > cfg["max_currency_exposure"] > 0:
        k = cfg["max_currency_exposure"] / worst
        notes.append(f"currency exposure {worst:.2f}x NAV > limit; scaled by {k:.2f}")
        for t in targets.values():
            t.units *= k
    return targets, notes


def run(frames: dict[str, pd.DataFrame], prices: dict[str, pd.DataFrame], regime: pd.DataFrame,
        asof: pd.Timestamp, db: DB, log=print, force_dry_run: bool = False) -> dict:
    cfg_rows = db.select("agent_config", {"select": "*", "id": "eq.1"})
    cfg = {**DEFAULT_CFG, **(cfg_rows[0] if cfg_rows else {})}
    live = bool(cfg["trading_enabled"]) and not force_dry_run
    today = asof.date()

    ob = Oanda()
    acct = ob.summary()
    if acct.get("currency") != "USD":
        raise RuntimeError(f"ORION expects a USD-denominated practice account, got {acct.get('currency')}")
    nav = float(acct["NAV"])
    syms = [s for s in INSTRUMENTS if s in frames]
    meta = ob.instruments(syms)
    quotes = ob.prices(syms)
    mids = {s: q["mid"] for s, q in quotes.items()}
    positions = ob.open_positions()
    current = {s: p["units"] for s, p in positions.items() if s in INSTRUMENTS}

    journal, orders = [], []

    # --- circuit breaker ----------------------------------------------------
    hist = db.select("equity_snapshots", {"select": "date,nav", "order": "date.asc"})
    peak = max([h["nav"] for h in hist] + [nav])
    dd = nav / peak - 1
    if dd <= -cfg["halt_drawdown"]:
        log("  HALT: drawdown circuit breaker triggered (details in admin journal)")
        journal.append({"date": today, "action": "halt", "summary": f"Drawdown {dd:.1%} breached the {cfg['halt_drawdown']:.0%} limit. Flattening and disabling trading.",
                        "detail": {"nav": nav, "peak": peak}})
        for sym, u in current.items():
            orders.append(_execute(ob, live, today, sym, -u, "flatten", None, close=True))
        if live:
            db.update("agent_config", {"id": 1}, {"trading_enabled": False, "halted_reason": f"drawdown {dd:.1%} on {today}"})
        _write(db, journal, orders)
        return _snapshot(db, ob, prices, today, log)

    scores = {s: float(frames[s]["composite"].loc[asof]) if asof in frames[s].index else float("nan") for s in syms}
    atrs = {s: float(atr_fn(prices[s], 20).loc[:asof].iloc[-1]) for s in syms}
    targets, notes = build_targets(cfg, nav, mids, current, scores, atrs)
    if notes:
        log(f"  {len(notes)} portfolio limit adjustment(s) applied (see admin journal)")

    for sym in syms:
        t = targets[sym]
        cur = current.get(sym, 0.0)
        prec = int(meta.get(sym, {}).get("tradeUnitsPrecision", 0))
        dp = int(meta.get(sym, {}).get("displayPrecision", 5))
        tgt_units = _round_units(t.units, prec)
        stop_s = f"{t.stop:.{dp}f}" if t.stop else None
        th = thesis(sym, frames[sym], prices[sym], regime.loc[asof] if asof in regime.index else pd.Series(dtype=object),
                    asof, atrs[sym], cfg["stop_atr_multiple"])
        tradeable = quotes.get(sym, {}).get("tradeable", True)
        base_detail = {"score": round(t.score, 3), "target_units": tgt_units, "current_units": cur, "stop": stop_s,
                       "nav": nav, "limits_notes": notes, "thesis": th}
        if not tradeable:
            journal.append({"date": today, "symbol": sym, "action": "skip", "summary": f"{sym} not tradeable now; no action.", "detail": base_detail})
            continue
        if np.sign(tgt_units) != np.sign(cur) and cur != 0:
            orders.append(_execute(ob, live, today, sym, -cur, "close", None, close=True))
            journal.append({"date": today, "symbol": sym, "action": "exit",
                            "summary": f"Closed {sym} ({cur:+,.0f} units): composite {t.score:+.2f} crossed the exit level.", "detail": base_detail})
            cur = 0.0
        if tgt_units == 0:
            if cur == 0:
                journal.append({"date": today, "symbol": sym, "action": "hold", "summary": f"{sym}: no position. Composite {t.score:+.2f} inside ±{cfg['entry_threshold']}.", "detail": base_detail})
            continue
        if cur == 0:
            orders.append(_execute(ob, live, today, sym, tgt_units, "open", stop_s))
            side = "long" if tgt_units > 0 else "short"
            journal.append({"date": today, "symbol": sym, "action": f"enter_{side}",
                            "summary": f"Entered {side} {sym} {abs(tgt_units):,.{prec}f} units, stop {stop_s}. Composite {t.score:+.2f}. {th['thesis']}",
                            "detail": base_detail})
            continue
        # same direction: resize only outside the band to limit turnover
        diff = tgt_units - cur
        if abs(diff) / abs(cur) > cfg["rebalance_band"]:
            diff = _round_units(diff, prec)
            if diff != 0:
                orders.append(_execute(ob, live, today, sym, diff, "resize", stop_s))
                journal.append({"date": today, "symbol": sym, "action": "resize",
                                "summary": f"Resized {sym} by {diff:+,.{prec}f} units toward risk target.", "detail": base_detail})
        else:
            journal.append({"date": today, "symbol": sym, "action": "hold",
                            "summary": f"Holding {sym} {cur:+,.0f} units. Composite {t.score:+.2f}.", "detail": base_detail})
        # ratchet stops in the favourable direction only
        if live and stop_s:
            for tr in ob.open_trades():
                if tr["instrument"] != sym:
                    continue
                old = float(tr.get("stopLossOrder", {}).get("price", "nan"))
                better = (not np.isfinite(old)) or (cur > 0 and t.stop > old) or (cur < 0 and t.stop < old)
                if better:
                    ob.set_trade_stop(tr["id"], stop_s)

    _write(db, journal, orders)
    # Logs and the return value are public (GitHub Actions logs, pipeline_runs table): no NAV, sizes or P&L.
    log(f"  agent: {'LIVE (practice)' if live else 'DRY RUN'}; {len(orders)} orders")
    return _snapshot(db, ob, prices, today, log)


def _execute(ob: Oanda, live: bool, today, sym: str, units: float, intent: str, stop: str | None, close: bool = False) -> dict:
    row = {"date": today, "symbol": sym, "units": units, "intent": intent, "stop_price": float(stop) if stop else None}
    if not live:
        return {**row, "status": "dry_run"}
    try:
        resp = ob.close_position(sym, -units) if close else ob.market_order(sym, units, stop, f"orion {intent} {today}")
        fill = resp.get("orderFillTransaction") or resp.get("longOrderFillTransaction") or resp.get("shortOrderFillTransaction") or {}
        status = "filled" if fill else "rejected"
        return {**row, "status": status, "broker_order_id": fill.get("orderID"),
                "fill_price": float(fill["price"]) if fill.get("price") else None, "response": resp}
    except Exception as e:  # noqa: BLE001
        return {**row, "status": "error", "error": str(e)[:500]}


def _write(db: DB, journal: list[dict], orders: list[dict]) -> None:
    db.upsert("journal", journal)
    db.upsert("orders", orders)


def _snapshot(db: DB, ob: Oanda, prices: dict, today, log) -> dict:
    acct = ob.summary()
    nav = float(acct["NAV"])
    pos = ob.open_positions()
    quotes = ob.prices(list(INSTRUMENTS))
    mids = {s: q["mid"] for s, q in quotes.items()}
    units = {s: p["units"] for s, p in pos.items() if s in INSTRUMENTS}
    w = notional_weights(units, mids, nav) if units else {}
    exp = currency_exposure(units, mids) if units else {}
    risk = portfolio_risk(w, prices)
    hist = db.select("equity_snapshots", {"select": "date,nav", "order": "date.asc"})
    navs = [h["nav"] for h in hist if h["date"] != str(today)] + [nav]
    peak = max(navs)
    first = navs[0]
    dd = nav / peak - 1
    db.upsert("equity_snapshots", [{
        "date": today, "nav": nav, "balance": float(acct["balance"]), "unrealized_pl": float(acct["unrealizedPL"]),
        "margin_used": float(acct["marginUsed"]), "gross_exposure": risk.get("gross"),
        "currency_exposure": {k: v / nav for k, v in exp.items()}, "portfolio_vol": risk.get("portfolio_vol"),
        "drawdown": dd, "risk": risk}], on_conflict="date")
    db.upsert("positions_snapshot", [{
        "date": today, "symbol": s, "units": p["units"], "avg_price": p["avg_price"], "unrealized_pl": p["unrealized_pl"],
        "notional_usd": w.get(s, 0) * nav, "weight": w.get(s)} for s, p in pos.items()], on_conflict="date,symbol")
    # Public: percentage index and drawdown only
    db.upsert("performance_public", [{"date": today, "nav_index": nav / first * 100, "drawdown": dd}], on_conflict="date")
    log("  snapshot written")
    return {"snapshot": "ok"}
