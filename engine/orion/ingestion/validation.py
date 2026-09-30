"""Data validation. Returns a list of issues; the pipeline records them and fails hard on 'error' level."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Issue:
    dataset: str
    level: str  # info | warn | error
    check: str
    detail: str

    def dict(self):
        return asdict(self)


def validate_prices(symbol: str, df: pd.DataFrame, max_stale_days: int = 5, asof: pd.Timestamp | None = None) -> list[Issue]:
    out: list[Issue] = []
    if df.empty:
        return [Issue(symbol, "error", "empty", "no price rows")]
    if df.index.duplicated().any():
        out.append(Issue(symbol, "error", "duplicates", f"{int(df.index.duplicated().sum())} duplicate dates"))
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        out.append(Issue(symbol, "error", "non_positive", "non-positive prices"))
    bad_hl = (df["high"] < df[["open", "close"]].max(axis=1) - 1e-12) | (df["low"] > df[["open", "close"]].min(axis=1) + 1e-12)
    if bad_hl.any():
        out.append(Issue(symbol, "warn", "ohlc_consistency", f"{int(bad_hl.sum())} bars with high/low outside open/close"))
    r = np.log(df["close"]).diff().dropna()
    if len(r) > 60:
        z = (r - r.rolling(60).mean()) / r.rolling(60).std()
        jumps = z.abs() > 8
        if jumps.any():
            dates = ", ".join(str(d.date()) for d in z[jumps].index[:5])
            out.append(Issue(symbol, "warn", "outlier_returns", f"{int(jumps.sum())} moves > 8 sigma ({dates})"))
    gaps = df.index.to_series().diff().dt.days
    big = gaps[gaps > 5]
    if len(big):
        out.append(Issue(symbol, "warn", "gaps", f"{len(big)} gaps > 5 days, largest {int(big.max())}d"))
    asof = asof or pd.Timestamp.now().normalize()
    stale = (asof - df.index[-1]).days
    if stale > max_stale_days:
        out.append(Issue(symbol, "error", "stale", f"last bar {df.index[-1].date()} is {stale} days old"))
    return out


def validate_series(sid: str, s: pd.Series, frequency: str, asof: pd.Timestamp | None = None) -> list[Issue]:
    out: list[Issue] = []
    if s.empty:
        return [Issue(sid, "error", "empty", "no observations")]
    asof = asof or pd.Timestamp.now().normalize()
    limit = {"daily": 7, "weekly": 16, "monthly": 75}.get(frequency, 30)
    stale = (asof - s.index[-1]).days
    if stale > limit:
        out.append(Issue(sid, "warn", "stale", f"last obs {s.index[-1].date()} is {stale} days old (limit {limit})"))
    d = s.diff().dropna()
    if len(d) > 60 and frequency == "daily":
        z = (d - d.rolling(60).mean()) / d.rolling(60).std()
        n = int((z.abs() > 10).sum())
        if n:
            out.append(Issue(sid, "warn", "outliers", f"{n} daily changes > 10 sigma"))
    return out
