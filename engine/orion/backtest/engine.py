"""Event-style daily backtester for the composite-signal rule.

Rule (per instrument), evaluated with information up to the close of day t-1 and executed on day t:
    ENTER LONG   if composite[t-1] >=  entry_threshold  and flat
    ENTER SHORT  if composite[t-1] <= -entry_threshold  and flat
    EXIT LONG    if composite[t-1] <   exit_threshold   or low[t]  <= stop
    EXIT SHORT   if composite[t-1] >  -exit_threshold   or high[t] >= stop
Entries / signal exits fill at the OPEN of day t, stops fill at the stop price (or the open if the
market gaps through it). Costs = half spread + slippage per side. Financing accrues daily.

Sizing: risk-based. Weight (notional / NAV) = risk_per_trade / (stop_distance / price), capped at
max_position_weight. With a 0.5% risk budget and a 2.5x ATR stop this gives roughly equal risk per trade.
Returns are computed on a constant-weight basis (exposure as a fraction of current NAV), a standard
research simplification that is documented as a limitation.
"""
from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS, StrategyParams
from ..features.core import atr as atr_fn
from .metrics import performance

CARRY_COLS = {"USD_JPY": "US_JP_2Y", "EUR_USD": "EU_US_2Y", "AUD_USD": "AU_US_2Y", "USD_CAD": "US_CA_2Y"}


def financing_rate(symbol: str, macro: pd.DataFrame | None, index: pd.DatetimeIndex) -> pd.Series:
    """Annual carry (in decimal) earned by a LONG position, before broker markup.

    FX: base-minus-quote 2Y yield differential (a proxy for the short-rate differential).
    Commodities: long positions pay USD rates (US 2Y proxy). Clearly an approximation.
    """
    if macro is None:
        return pd.Series(0.0, index=index)
    col = CARRY_COLS.get(symbol)
    if col and col in macro:
        return (macro[col].reindex(index).ffill().fillna(0) / 100)
    if "US2Y" in macro:
        return -(macro["US2Y"].reindex(index).ffill().fillna(0) / 100)
    return pd.Series(0.0, index=index)


def run_instrument(symbol: str, px: pd.DataFrame, signal: pd.Series, p: StrategyParams,
                   macro: pd.DataFrame | None = None, start=None, end=None) -> tuple[pd.Series, pd.Series, list[dict]]:
    inst = INSTRUMENTS[symbol]
    df = px[["open", "high", "low", "close"]].copy()
    df["sig"] = signal.reindex(df.index)
    df["atr"] = atr_fn(px, p.atr_window)
    df["fin"] = financing_rate(symbol, macro, df.index)
    if start is not None:
        df = df.loc[pd.Timestamp(start) - pd.Timedelta(days=10):]
    if end is not None:
        df = df.loc[:pd.Timestamp(end)]
    df = df.dropna(subset=["open", "close"])
    cost_side = (inst.spread_bps / 2 + inst.slippage_bps) / 1e4

    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    sig, atr, fin = df["sig"].to_numpy(), df["atr"].to_numpy(), df["fin"].to_numpy()
    dates = df.index
    n = len(df)
    ret = np.zeros(n)
    wts = np.zeros(n)
    trades: list[dict] = []
    pos, w, stop, entry_px, entry_i, trade_ret = 0, 0.0, np.nan, np.nan, -1, 0.0

    for i in range(1, n):
        s_prev = sig[i - 1]
        days = max((dates[i] - dates[i - 1]).days, 1)
        r_i = 0.0
        exited = False
        if pos != 0:
            ref = c[i - 1]
            exit_px, reason = None, None
            if pos > 0 and l[i] <= stop:
                exit_px, reason = min(o[i], stop), "stop"
            elif pos < 0 and h[i] >= stop:
                exit_px, reason = max(o[i], stop), "stop"
            elif np.isfinite(s_prev) and ((pos > 0 and s_prev < p.exit_threshold) or (pos < 0 and s_prev > -p.exit_threshold)):
                exit_px, reason = o[i], "signal"
            if exit_px is not None:
                r_i += pos * w * (exit_px / ref - 1) - w * cost_side
                exited = True
            else:
                r_i += pos * w * (c[i] / ref - 1)
            r_i += w * (pos * fin[i] - p.financing_markup_annual) * days / 365
            trade_ret += r_i
            if exited:
                trades.append({"symbol": symbol, "direction": pos, "entry_date": dates[entry_i].date(), "exit_date": dates[i].date(),
                               "entry_price": entry_px, "exit_price": float(exit_px), "weight": w,
                               "return_pct": trade_ret, "bars": i - entry_i, "exit_reason": reason})
                pos, w, stop, trade_ret = 0, 0.0, np.nan, 0.0
        if pos == 0 and not exited and np.isfinite(s_prev) and np.isfinite(atr[i - 1]) and atr[i - 1] > 0:
            d = 1 if s_prev >= p.entry_threshold else -1 if s_prev <= -p.entry_threshold else 0
            if d != 0:
                stop_dist = p.stop_atr_multiple * atr[i - 1]
                w = min(p.risk_per_trade / (stop_dist / o[i]), p.max_position_weight)
                pos, entry_px, entry_i = d, float(o[i]), i
                stop = o[i] - d * stop_dist
                entry_r = pos * w * (c[i] / o[i] - 1) - w * cost_side
                # same-day stop-out
                if (pos > 0 and l[i] <= stop) or (pos < 0 and h[i] >= stop):
                    entry_r = pos * w * (stop / o[i] - 1) - 2 * w * cost_side
                    trades.append({"symbol": symbol, "direction": pos, "entry_date": dates[i].date(), "exit_date": dates[i].date(),
                                   "entry_price": entry_px, "exit_price": float(stop), "weight": w,
                                   "return_pct": entry_r, "bars": 0, "exit_reason": "stop"})
                    pos, w, stop = 0, 0.0, np.nan
                    trade_ret = 0.0
                else:
                    trade_ret = entry_r
                r_i += entry_r
        ret[i] = r_i
        wts[i] = pos * w
    if pos != 0:
        trades.append({"symbol": symbol, "direction": pos, "entry_date": dates[entry_i].date(), "exit_date": None,
                       "entry_price": entry_px, "exit_price": float(c[-1]), "weight": w, "return_pct": trade_ret,
                       "bars": n - 1 - entry_i, "exit_reason": "open"})
    r = pd.Series(ret, index=dates, name=symbol)
    wt = pd.Series(wts, index=dates, name=symbol)
    if start is not None:
        r, wt = r.loc[pd.Timestamp(start):], wt.loc[pd.Timestamp(start):]
        trades = [t for t in trades if pd.Timestamp(t["entry_date"]) >= pd.Timestamp(start)]
    return r, wt, trades


def run_portfolio(prices: dict[str, pd.DataFrame], signals: dict[str, pd.Series], p: StrategyParams,
                  macro: pd.DataFrame | None = None, start=None, end=None) -> dict:
    rets, wts, trades = {}, {}, []
    for sym, px in prices.items():
        if sym not in signals:
            continue
        r, w, t = run_instrument(sym, px, signals[sym], p, macro, start, end)
        rets[sym], wts[sym] = r, w
        trades += t
    R = pd.DataFrame(rets).fillna(0)
    W = pd.DataFrame(wts).fillna(0)
    # Gross leverage cap: scale the whole book when yesterday's gross exposure exceeds the limit
    gross = W.abs().sum(axis=1).shift(1).fillna(0)
    scale = np.minimum(1.0, p.max_gross_leverage / gross.replace(0, np.nan)).fillna(1.0)
    port = R.sum(axis=1) * scale
    tdf = pd.DataFrame(trades)
    return {
        "returns": port, "by_instrument": R.mul(scale, axis=0), "weights": W.mul(scale, axis=0), "trades": tdf,
        "metrics": performance(port, tdf, W), "params": asdict(p),
    }
