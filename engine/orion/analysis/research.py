"""'What changed?', deterministic trade theses, and scenario analysis.

All text here is assembled from computed numbers with fixed templates, so nothing is invented.
An LLM layer (later phase) may rephrase these payloads but must not add facts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from ..signals.engine import COMPONENTS, compute_all, decompose, label

MACRO_WATCH = {
    "US2Y": ("US 2Y yield", "bp", 100), "US10Y": ("US 10Y yield", "bp", 100),
    "US10Y_REAL": ("US 10Y real yield", "bp", 100), "US10Y_BE": ("US 10Y breakeven", "bp", 100),
    "JP2Y": ("Japan 2Y yield", "bp", 100), "EU2Y": ("Euro 2Y yield", "bp", 100),
    "AU2Y": ("Australia 2Y yield", "bp", 100), "CA2Y": ("Canada 2Y yield", "bp", 100),
    "US_JP_2Y": ("US-Japan 2Y spread", "bp", 100), "EU_US_2Y": ("Euro-US 2Y spread", "bp", 100),
    "AU_US_2Y": ("Australia-US 2Y spread", "bp", 100), "US_CA_2Y": ("US-Canada 2Y spread", "bp", 100),
    "VIX": ("VIX", "pts", 1), "USD_BROAD": ("Broad USD index", "%", None),
    "WTI_ROLL_YIELD": ("WTI roll yield (ann.)", "pp", 1),
}

HORIZONS = {"1d": 1, "1w": 5, "1m": 21}


def _pctile(s: pd.Series, window: int = 756) -> float | None:
    x = s.dropna().iloc[-window:]
    if len(x) < 60:
        return None
    return round(float((x <= x.iloc[-1]).mean()), 2)


def what_changed(macro: pd.DataFrame, prices: dict, signals: dict[str, pd.DataFrame], asof: pd.Timestamp) -> dict:
    out = {"asof": str(asof.date()), "macro": [], "markets": [], "signals": [], "headlines": []}
    m = macro.loc[:asof]
    for col, (name, unit, mult) in MACRO_WATCH.items():
        if col not in m or m[col].dropna().empty:
            continue
        s = m[col].dropna()
        row = {"id": col, "name": name, "level": round(float(s.iloc[-1]), 3), "unit": unit, "percentile_3y": _pctile(s)}
        for h, n in HORIZONS.items():
            if len(s) > n:
                if mult is None:
                    row[h] = round((float(s.iloc[-1]) / float(s.iloc[-1 - n]) - 1) * 100, 2)
                else:
                    row[h] = round((float(s.iloc[-1]) - float(s.iloc[-1 - n])) * mult, 1)
        out["macro"].append(row)
    for sym, df in prices.items():
        c = df["close"].loc[:asof].dropna()
        if len(c) < 30:
            continue
        # No raw price levels here: this payload is public and OANDA prices are not ours to redistribute.
        r = {"symbol": sym, "name": INSTRUMENTS[sym].name, "percentile_3y": _pctile(c)}
        for h, n in HORIZONS.items():
            r[h] = round((float(c.iloc[-1]) / float(c.iloc[-1 - n]) - 1) * 100, 2)
        out["markets"].append(r)
    for sym, sdf in signals.items():
        s = sdf.loc[:asof]
        if s["composite"].dropna().empty:
            continue
        now = s.iloc[-1]
        wk = s.iloc[-6] if len(s) > 6 else s.iloc[0]
        comp_names = [c.name for c in COMPONENTS[sym] if c.name in s.columns]
        deltas = {n: float(now[n] - wk[n]) for n in comp_names if pd.notna(now[n]) and pd.notna(wk[n])}
        driver = max(deltas, key=lambda k: abs(deltas[k])) if deltas else None
        out["signals"].append({
            "symbol": sym, "composite": round(float(now["composite"]), 2),
            "change_1w": round(float(now["composite"] - wk["composite"]), 2) if pd.notna(wk["composite"]) else None,
            "label": label(now["composite"]), "label_1w_ago": label(wk["composite"]),
            "main_driver_1w": driver, "driver_change": round(deltas[driver], 2) if driver else None,
        })
    # Headlines: largest standardised moves, phrased from numbers only
    heads = []
    for row in out["macro"]:
        if row.get("1w") is not None and row["unit"] == "bp" and abs(row["1w"]) >= 10:
            up = row["1w"] > 0
            verb = ("widened" if up else "narrowed") if "spread" in row["name"] else ("rose" if up else "fell")
            heads.append((abs(row["1w"]) / 10, f"{row['name']} {verb} {abs(row['1w']):.0f} bp this week."))
    for s in out["signals"]:
        if s["label"] != s["label_1w_ago"]:
            heads.append((2 + abs(s["change_1w"] or 0), f"{INSTRUMENTS[s['symbol']].name} signal moved from {s['label_1w_ago']} to {s['label']} ({s['composite']:+.2f}), led by {s['main_driver_1w']}."))
    for mk in out["markets"]:
        if abs(mk.get("1w", 0)) >= 2.5:
            heads.append((abs(mk["1w"]) / 2.5, f"{mk['name']} {'up' if mk['1w'] > 0 else 'down'} {abs(mk['1w']):.1f}% on the week."))
    out["headlines"] = [h for _, h in sorted(heads, key=lambda x: -x[0])[:6]]
    return out


def thesis(sym: str, sdf: pd.DataFrame, prices: pd.DataFrame, regime_row: pd.Series, asof: pd.Timestamp,
           atr_value: float, stop_mult: float) -> dict:
    inst = INSTRUMENTS[sym]
    row = sdf.loc[asof]
    comp = decompose(sym, row)
    score = float(row["composite"]) if pd.notna(row["composite"]) else float("nan")
    lab = label(score)
    direction = 1 if score > 0 else -1
    ranked = sorted([(k, v) for k, v in comp.items() if v["value"] is not None], key=lambda kv: -abs(kv[1]["contribution"]))
    support = [k for k, v in ranked if np.sign(v["contribution"]) == direction][:2]
    against = [k for k, v in ranked if np.sign(v["contribution"]) == -direction][:2]
    close = float(prices["close"].loc[asof])
    stop = close - direction * stop_mult * atr_value if np.isfinite(atr_value) else None
    verb = {"Positive": "supportive", "Negative": "negative", "Neutral": "mixed", "No data": "unavailable"}[lab]
    lines = [f"The composite signal for {inst.name} is {score:+.2f} ({verb})."]
    if support:
        lines.append("Main drivers: " + ", ".join(f"{k} ({comp[k]['contribution']:+.2f})" for k in support) + ".")
    if against:
        lines.append("Offsetting: " + ", ".join(f"{k} ({comp[k]['contribution']:+.2f})" for k in against) + ".")
    lines.append(f"Current regime: {regime_row.get('label', 'n/a')}.")
    return {
        "symbol": sym, "name": inst.name, "asof": str(asof.date()), "score": round(score, 2), "label": lab,
        "bias": "Long" if lab == "Positive" else "Short" if lab == "Negative" else "No position",
        "thesis": " ".join(lines),
        "components": comp,
        "catalysts": list(inst.catalysts),
        "risks": list(inst.risks),
        "invalidation": {
            "signal": f"Composite crosses back through 0.00 (now {score:+.2f})",
            "price": (f"Daily close through a {stop_mult}x ATR stop ({stop_mult * atr_value / close * 100:.1f}% from last close)"
                      if stop else None),
        },
        "horizon": "1-4 weeks (signals use 1-6 month inputs; rebalanced daily)",
        "key_variables": [comp[k]["description"] for k in list(comp)[:4]],
        "disclaimer": "Research output generated from rules and data. Not investment advice.",
    }


SCENARIOS = {
    "us2y_up_25": ("US 2Y yield +25 bp", {"US2Y": 0.25}),
    "us2y_down_25": ("US 2Y yield -25 bp", {"US2Y": -0.25}),
    "real_yield_up_20": ("US 10Y real yield +20 bp", {"US10Y_REAL": 0.20}),
    "vix_up_5": ("VIX +5 pts", {"VIX": 5.0}),
    "usd_up_2pct": ("Broad USD +2%", {"USD_BROAD": 0.02}),
}


def scenarios(macro: pd.DataFrame, prices: dict, asof: pd.Timestamp) -> dict:
    """Signal impact of an instantaneous shock applied to today's inputs.

    This answers 'how would the *signals* respond', using the same formulas as the live engine.
    It is not a price forecast.
    """
    window = macro.loc[:asof].iloc[-800:].copy()
    pw = {s: df.loc[:asof].iloc[-800:] for s, df in prices.items()}
    base = {s: f["composite"].iloc[-1] for s, f in compute_all(window, pw).items()}
    out = {"asof": str(asof.date()), "note": "Change in composite signal under an instantaneous shock. Not a price forecast.",
           "scenarios": []}
    for key, (name, shocks) in SCENARIOS.items():
        m = window.copy()
        for col, v in shocks.items():
            if col not in m:
                continue
            if col == "USD_BROAD":
                m.loc[m.index[-1], col] *= (1 + v)
            else:
                m.loc[m.index[-1], col] += v
        # recompute derived spreads
        for a, b, d in (("US2Y", "JP2Y", "US_JP_2Y"), ("EU2Y", "US2Y", "EU_US_2Y"), ("AU2Y", "US2Y", "AU_US_2Y"), ("US2Y", "CA2Y", "US_CA_2Y")):
            if {a, b, d} <= set(m.columns):
                m[d] = m[a] - m[b]
        shocked = {s: f["composite"].iloc[-1] for s, f in compute_all(m, pw).items()}
        out["scenarios"].append({"id": key, "name": name, "impact": {
            s: round(float(shocked[s] - base[s]), 2) for s in base if pd.notna(base[s]) and pd.notna(shocked.get(s))}})
    return out
