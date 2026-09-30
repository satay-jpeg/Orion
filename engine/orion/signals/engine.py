"""Explainable signal engine.

Every instrument gets a handful of independent components, each already in z-units (roughly N(0,1),
clipped at +/-3) and signed so that POSITIVE = supportive for the instrument *as quoted*
(e.g. positive USD_JPY = USD up vs JPY).

Composite = weighted average of available components. Default weights are equal: with
~15 years of daily data and several correlated inputs, equal weights are the least overfit
choice (DeMiguel, Garlappi & Uppal 2009 make the same argument for portfolios). Component
predictive power is *reported* per walk-forward window (see backtest/walkforward.py) rather than
used to fit weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from ..config import CHANGE_WINDOW, INSTRUMENTS, MIN_COMPLETENESS, NEUTRAL_BAND, Z_WINDOW_LONG
from ..features.core import realized_vol, risk_adj_return, trend_score, zscore


@dataclass
class Component:
    name: str
    description: str
    requires: tuple[str, ...]           # macro columns / price symbols needed
    fn: Callable[[pd.DataFrame, dict], pd.Series]
    weight: float = 1.0


def _chg(x: pd.Series, n: int = CHANGE_WINDOW) -> pd.Series:
    return x - x.shift(n)


def _close(prices: dict, sym: str) -> pd.Series:
    return prices[sym]["close"]


def rate_diff(col: str, sign: float = 1.0):
    return lambda m, p: sign * zscore(_chg(m[col]))


def carry(col: str, sign: float = 1.0):
    return lambda m, p: sign * zscore(m[col], window=Z_WINDOW_LONG)


def vix_impulse(sign: float = -1.0):
    # rising VIX -> risk-off; sign chosen per instrument
    return lambda m, p: sign * zscore(_chg(m["VIX"]))


def trend(sym: str):
    return lambda m, p: trend_score(_close(p, sym))


def usd_impulse(sign: float = -1.0):
    return lambda m, p: sign * zscore(_chg(np.log(m["USD_BROAD"])))


def carry_vol_filter(sym: str, carry_col: str):
    """High realised vol hurts carry trades: penalise in the direction of carry."""
    def f(m, p):
        v = zscore(realized_vol(_close(p, sym)))
        return -v * np.sign(m[carry_col])
    return f


def cross_asset(sym: str, sign: float = 1.0):
    return lambda m, p: sign * risk_adj_return(_close(p, sym))


COMPONENTS: dict[str, list[Component]] = {
    "USD_JPY": [
        Component("rates", "20d change in US-Japan 2Y spread (z)", ("US_JP_2Y",), rate_diff("US_JP_2Y")),
        Component("carry", "US-Japan 2Y spread level vs 3y history (z)", ("US_JP_2Y",), carry("US_JP_2Y")),
        Component("risk", "Inverse 20d change in VIX (z); risk-off supports JPY", ("VIX",), vix_impulse(-1)),
        Component("volatility", "Realised vol penalty in direction of carry", ("US_JP_2Y",),
                  carry_vol_filter("USD_JPY", "US_JP_2Y")),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("USD_JPY")),
    ],
    "EUR_USD": [
        Component("rates", "20d change in Euro-US 2Y spread (z)", ("EU_US_2Y",), rate_diff("EU_US_2Y")),
        Component("carry", "Euro-US 2Y spread level vs 3y history (z)", ("EU_US_2Y",), carry("EU_US_2Y")),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("EUR_USD")),
    ],
    "AUD_USD": [
        Component("rates", "20d change in Australia-US 2Y spread (z)", ("AU_US_2Y",), rate_diff("AU_US_2Y")),
        Component("carry", "Australia-US 2Y spread level vs 3y history (z)", ("AU_US_2Y",), carry("AU_US_2Y")),
        Component("risk", "Inverse 20d change in VIX (z)", ("VIX",), vix_impulse(-1)),
        Component("metals", "Copper 60d risk-adjusted return", ("@XCU_USD",), cross_asset("XCU_USD")),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("AUD_USD")),
    ],
    "USD_CAD": [
        Component("rates", "20d change in US-Canada 2Y spread (z)", ("US_CA_2Y",), rate_diff("US_CA_2Y")),
        Component("carry", "US-Canada 2Y spread level vs 3y history (z)", ("US_CA_2Y",), carry("US_CA_2Y")),
        Component("oil", "Inverse Brent 60d risk-adjusted return (oil up = CAD up)", ("@BCO_USD",),
                  cross_asset("BCO_USD", -1)),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("USD_CAD")),
    ],
    "XAU_USD": [
        Component("real_yield", "Inverse 20d change in US 10Y real yield (z)", ("US10Y_REAL",),
                  rate_diff("US10Y_REAL", -1)),
        Component("usd", "Inverse 20d change in broad USD index (z)", ("USD_BROAD",), usd_impulse(-1)),
        Component("breakevens", "20d change in US 10Y breakeven inflation (z)", ("US10Y_BE",), rate_diff("US10Y_BE")),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("XAU_USD")),
    ],
    "BCO_USD": [
        Component("curve", "WTI front-month roll yield vs 1y history (z); + = backwardation", ("WTI_ROLL_YIELD",),
                  lambda m, p: zscore(m["WTI_ROLL_YIELD"])),
        Component("inventories", "Inverse YoY change in US crude stocks (z)", ("CRUDE_STOCKS_YOY",),
                  lambda m, p: -zscore(m["CRUDE_STOCKS_YOY"])),
        Component("growth", "Chicago Fed activity index (3m avg) vs 3y history (z)", ("CFNAI_MA3",),
                  lambda m, p: zscore(m["CFNAI_MA3"], window=Z_WINDOW_LONG)),
        Component("usd", "Inverse 20d change in broad USD index (z)", ("USD_BROAD",), usd_impulse(-1)),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("BCO_USD")),
    ],
    "XCU_USD": [
        Component("growth", "Chicago Fed activity index (3m avg) vs 3y history (z)", ("CFNAI_MA3",),
                  lambda m, p: zscore(m["CFNAI_MA3"], window=Z_WINDOW_LONG)),
        Component("usd", "Inverse 20d change in broad USD index (z)", ("USD_BROAD",), usd_impulse(-1)),
        Component("risk", "Inverse 20d change in VIX (z)", ("VIX",), vix_impulse(-1)),
        Component("trend", "Vol-adjusted 1/3/6m momentum", (), trend("XCU_USD")),
    ],
}


def _available(req: tuple[str, ...], macro: pd.DataFrame, prices: dict) -> bool:
    for r in req:
        if r.startswith("@"):
            if r[1:] not in prices:
                return False
        elif r not in macro.columns or macro[r].notna().sum() == 0:
            return False
    return True


def compute_components(symbol: str, macro: pd.DataFrame, prices: dict) -> pd.DataFrame:
    cols = {}
    for c in COMPONENTS[symbol]:
        if symbol not in prices or not _available(c.requires, macro, prices):
            continue
        cols[c.name] = c.fn(macro, prices).reindex(macro.index)
    return pd.DataFrame(cols, index=macro.index)


def composite(symbol: str, comps: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Weighted average of available components (weights renormalised when a component is missing)."""
    spec = {c.name: c.weight for c in COMPONENTS[symbol]}
    if weights:
        spec.update(weights)
    w = pd.Series(spec)
    w = w[w.index.isin(comps.columns)]
    avail = comps[w.index].notna()
    wmat = avail.mul(w, axis=1)
    wsum = wmat.sum(axis=1)
    score = (comps[w.index].fillna(0) * wmat).sum(axis=1) / wsum.replace(0, np.nan)
    total_w = sum(spec.values())
    completeness = wsum / total_w
    # A composite built from too few components is not reported (and therefore never traded)
    score = score.where(completeness >= MIN_COMPLETENESS)
    return pd.DataFrame({"composite": score, "completeness": completeness})


def label(x: float) -> str:
    if x is None or not np.isfinite(x):
        return "No data"
    if x >= NEUTRAL_BAND:
        return "Positive"
    if x <= -NEUTRAL_BAND:
        return "Negative"
    return "Neutral"


def compute_all(macro: pd.DataFrame, prices: dict) -> dict[str, pd.DataFrame]:
    """Return per-symbol frames: component columns + composite + completeness."""
    out = {}
    for sym in INSTRUMENTS:
        if sym not in prices:
            continue
        comps = compute_components(sym, macro, prices)
        comp = composite(sym, comps)
        out[sym] = pd.concat([comps, comp], axis=1)
    return out


def decompose(symbol: str, row: pd.Series) -> dict:
    """Contribution of each component to the composite on one date (sums to the composite)."""
    spec = {c.name: c for c in COMPONENTS[symbol]}
    present = [n for n in spec if n in row.index and pd.notna(row[n])]
    wsum = sum(spec[n].weight for n in present) or np.nan
    out = {}
    for n in present:
        w = spec[n].weight / wsum
        out[n] = {
            "value": round(float(row[n]), 3),
            "weight": round(float(w), 3),
            "contribution": round(float(row[n] * w), 3),
            "description": spec[n].description,
        }
    for n in spec:
        if n not in out:
            out[n] = {"value": None, "weight": 0.0, "contribution": 0.0,
                      "description": spec[n].description + " (data unavailable)"}
    return out
