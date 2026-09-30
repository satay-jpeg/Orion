"""Risk engine: position sizing, currency/commodity exposure, correlation-aware portfolio risk."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS


def quote_to_usd(symbol: str, price: float, prices_now: dict[str, float]) -> float:
    """USD value of 1 unit of the quote currency."""
    q = INSTRUMENTS[symbol].quote
    if q == "USD":
        return 1.0
    # quote is JPY or CAD in our universe -> USD_JPY / USD_CAD quoted as quote per USD
    pair = f"USD_{q}"
    px = prices_now.get(pair, price if symbol == pair else None)
    if not px:
        raise ValueError(f"need {pair} price to convert {q} to USD")
    return 1.0 / px


def position_size(account_usd: float, risk_pct: float, entry: float, stop: float, symbol: str,
                  prices_now: dict[str, float]) -> dict:
    """Units such that hitting the stop loses account_usd * risk_pct (before gap risk)."""
    dist = abs(entry - stop)
    if dist <= 0:
        raise ValueError("stop must differ from entry")
    q2usd = quote_to_usd(symbol, entry, prices_now)
    risk_usd = account_usd * risk_pct
    units = risk_usd / (dist * q2usd)
    notional_usd = units * entry * q2usd
    pip = 0.01 if INSTRUMENTS[symbol].quote == "JPY" else 0.0001
    return {"units": units, "risk_usd": risk_usd, "notional_usd": notional_usd,
            "leverage": notional_usd / account_usd, "stop_distance": dist,
            "stop_distance_pips": dist / pip if INSTRUMENTS[symbol].asset_class == "fx" else None}


def currency_exposure(positions: dict[str, float], prices_now: dict[str, float]) -> dict[str, float]:
    """Decompose positions (units, signed) into USD-equivalent exposure per currency / commodity leg.

    Long 100k USD_JPY  -> USD +100k, JPY -100k (in USD terms)
    Long 10 XAU_USD    -> XAU +10*px, USD -10*px
    """
    exp: dict[str, float] = {}
    for sym, units in positions.items():
        if not units:
            continue
        inst = INSTRUMENTS[sym]
        px = prices_now[sym]
        quote_notional_usd = units * px * quote_to_usd(sym, px, prices_now)
        exp[inst.base] = exp.get(inst.base, 0.0) + quote_notional_usd
        exp[inst.quote] = exp.get(inst.quote, 0.0) - quote_notional_usd
    return exp


def notional_weights(positions: dict[str, float], prices_now: dict[str, float], nav: float) -> dict[str, float]:
    out = {}
    for sym, units in positions.items():
        px = prices_now[sym]
        out[sym] = units * px * quote_to_usd(sym, px, prices_now) / nav
    return out


def portfolio_risk(weights: dict[str, float], prices: dict[str, pd.DataFrame], window: int = 60) -> dict:
    syms = [s for s, w in weights.items() if w]
    if not syms:
        return {"portfolio_vol": 0.0, "correlation": {}, "risk_contribution": {}, "gross": 0.0, "net_usd": 0.0}
    rets = pd.DataFrame({s: np.log(prices[s]["close"]).diff() for s in syms}).dropna().iloc[-window:]
    cov = rets.cov() * 252
    w = np.array([weights[s] for s in syms])
    var = float(w @ cov.values @ w)
    vol = np.sqrt(max(var, 0))
    mrc = cov.values @ w
    rc = {s: float(w[i] * mrc[i] / var) if var > 0 else 0.0 for i, s in enumerate(syms)}
    standalone = float(np.sum(np.abs(w) * np.sqrt(np.diag(cov.values))))
    gross = float(np.abs(w).sum())
    return {
        "portfolio_vol": vol,
        "sum_standalone_vol": standalone,
        "diversification_ratio": standalone / vol if vol > 0 else None,
        "correlation": rets.corr().round(2).to_dict(),
        "risk_contribution": rc,
        "gross": gross,
        "concentration_hhi": float(((np.abs(w) / gross) ** 2).sum()) if gross else None,
    }


def correlation_matrix(prices: dict[str, pd.DataFrame], window: int = 60) -> dict:
    rets = pd.DataFrame({s: np.log(df["close"]).diff() for s, df in prices.items()}).dropna().iloc[-window:]
    return rets.corr().round(2).to_dict()
