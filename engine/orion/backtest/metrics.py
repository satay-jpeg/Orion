from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def performance(returns: pd.Series, trades: pd.DataFrame | None = None, weights: pd.DataFrame | None = None) -> dict:
    r = returns.dropna()
    if len(r) < 2:
        return {}
    eq = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    total = float(eq.iloc[-1] - 1)
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else float("nan")
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
    dd = drawdown(eq)
    out = {
        "start": str(r.index[0].date()), "end": str(r.index[-1].date()), "days": int(len(r)),
        "total_return": total, "cagr": cagr, "ann_vol": vol,
        "sharpe": float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else float("nan"),
        "sortino": float(r.mean() * TRADING_DAYS / downside) if downside and downside > 0 else float("nan"),
        "max_drawdown": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else float("nan"),
        "best_day": float(r.max()), "worst_day": float(r.min()),
        "pct_days_invested": float((weights.abs().sum(axis=1) > 0).mean()) if weights is not None and len(weights) else None,
    }
    if weights is not None and len(weights):
        w = weights.reindex(r.index).fillna(0)
        out["turnover_annual"] = float(w.diff().abs().sum(axis=1).mean() * TRADING_DAYS)
        out["avg_gross_leverage"] = float(w.abs().sum(axis=1).mean())
    if trades is not None and len(trades):
        t = trades.dropna(subset=["return_pct"])
        wins, losses = t[t["return_pct"] > 0], t[t["return_pct"] <= 0]
        out.update({
            "trades": int(len(t)),
            "win_rate": float(len(wins) / len(t)) if len(t) else float("nan"),
            "profit_factor": float(wins["return_pct"].sum() / -losses["return_pct"].sum()) if len(losses) and losses["return_pct"].sum() < 0 else float("nan"),
            "avg_trade": float(t["return_pct"].mean()),
            "avg_holding_days": float(t["bars"].mean()),
        })
    return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in out.items()}


def monthly_returns(returns: pd.Series) -> list[dict]:
    m = (1 + returns.dropna()).resample("ME").prod() - 1
    return [{"month": d.strftime("%Y-%m"), "return": float(v)} for d, v in m.items()]
