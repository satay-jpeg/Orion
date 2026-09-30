"""Rule-based market regime classification + historical analogues.

Each dimension uses one transparent rule on point-in-time data. Thresholds are round numbers chosen
ex-ante and documented in docs/METHODOLOGY.md; they are not optimised.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..features.core import realized_vol, zscore


def classify(macro: pd.DataFrame, prices: dict) -> pd.DataFrame:
    idx = macro.index
    out = pd.DataFrame(index=idx)

    # Growth: Chicago Fed National Activity Index, 3m average. The Chicago Fed notes that
    # CFNAI-MA3 < -0.70 has historically signalled recession; 0 = trend growth.
    g = macro.get("CFNAI_MA3")
    out["growth_x"] = g
    out["growth"] = np.select([g > 0.20, g < -0.35], ["Strong", "Weak"], "Neutral") if g is not None else None

    # Inflation: 3-month change in CPI YoY (pp), with breakevens as tie-breaker
    cpi = macro.get("US_CPI_YOY")
    if cpi is not None:
        d = cpi - cpi.shift(63)
        out["inflation_x"] = d
        out["inflation"] = np.select([d > 0.25, d < -0.25], ["Rising", "Falling"], "Stable")

    # Risk: VIX vs its own 1y distribution
    if "VIX" in macro:
        z = zscore(macro["VIX"])
        out["risk_x"] = z
        out["risk"] = np.select([z > 1.0, z < -0.5], ["Risk-off", "Risk-on"], "Neutral")

    # USD: 60d log change of broad dollar index, standardised
    if "USD_BROAD" in macro:
        chg = np.log(macro["USD_BROAD"]).diff(60)
        z = zscore(chg)
        out["usd_x"] = z
        out["usd"] = np.select([z > 0.5, z < -0.5], ["Strong", "Weak"], "Neutral")

    # Cross-asset volatility: average percentile of 20d realised vol across instruments
    pct = []
    for sym, df in prices.items():
        rv = realized_vol(df["close"]).reindex(idx)
        pct.append(rv.rolling(756, min_periods=252).rank(pct=True))
    if pct:
        vp = pd.concat(pct, axis=1).mean(axis=1)
        out["volatility_x"] = vp
        out["volatility"] = np.select([vp > 0.8, vp < 0.25], ["High", "Low"], "Normal")

    for col in ("growth", "inflation", "risk", "usd", "volatility"):
        if col not in out:
            out[col] = None
        # np.select on NaN input yields the default; mark missing input explicitly
        xcol = f"{col}_x"
        if xcol in out:
            out.loc[out[xcol].isna(), col] = None
    out["label"] = out.apply(_label, axis=1)
    return out


def _label(r: pd.Series) -> str:
    risk, usd = r.get("risk"), r.get("usd")
    parts = []
    if risk == "Risk-off":
        parts.append("RISK-OFF")
    elif risk == "Risk-on":
        parts.append("RISK-ON")
    else:
        parts.append("MIXED RISK")
    if usd == "Strong":
        parts.append("USD SUPPORTIVE")
    elif usd == "Weak":
        parts.append("USD HEADWIND")
    elif r.get("growth") == "Weak":
        parts.append("GROWTH SCARE")
    elif r.get("inflation") == "Rising":
        parts.append("REFLATION")
    else:
        parts.append("RANGE")
    return " / ".join(parts)


DIMS = ("growth", "inflation", "risk", "usd", "volatility")


def analogues(regime: pd.DataFrame, prices: dict, asof: pd.Timestamp, min_match: int = 4,
              horizons=(5, 20, 60), exclude_recent_days: int = 90) -> dict:
    """Historical dates sharing >= min_match of the 5 regime states with `asof`.

    Returns episodes (contiguous runs) and the distribution of subsequent returns for each instrument.
    Descriptive only: overlapping windows mean observations are not independent.
    """
    cur = regime.loc[asof, list(DIMS)]
    dims = [d for d in DIMS if pd.notna(cur[d])]
    min_match = min(min_match, len(dims) - 1)
    hist = regime.loc[: asof - pd.Timedelta(days=exclude_recent_days), dims].dropna()
    if hist.empty or len(dims) < 3:
        return {"asof": str(asof.date()), "current": cur.to_dict(), "episodes": [], "forward": {},
                "caveat": "Not enough regime data to find analogues."}
    matches = (hist == cur[dims].values).sum(axis=1)
    sel = matches[matches >= min_match].index
    episodes = []
    if len(sel):
        s = pd.Series(sel)
        grp = (s.diff().dt.days > 10).cumsum()
        for _, g in s.groupby(grp):
            if len(g) >= 5:
                episodes.append({"start": str(g.iloc[0].date()), "end": str(g.iloc[-1].date()), "days": int(len(g))})
    fwd = {}
    for sym, df in prices.items():
        c = df["close"]
        res = {}
        for h in horizons:
            r = (c.shift(-h) / c - 1).reindex(sel).dropna()
            if len(r) >= 20:
                res[f"{h}d"] = {"median": round(float(r.median()) * 100, 2), "hit_rate": round(float((r > 0).mean()), 2),
                                "p25": round(float(r.quantile(.25)) * 100, 2), "p75": round(float(r.quantile(.75)) * 100, 2),
                                "n": int(len(r))}
        fwd[sym] = res
    return {"asof": str(asof.date()), "current": cur.to_dict(), "min_match": min_match, "dimensions_used": dims,
            "matching_days": int(len(sel)), "episodes": episodes[-12:], "forward": fwd,
            "caveat": "Descriptive only. Overlapping windows; not a forecast."}
