"""Feature primitives and the point-in-time panel.

Look-ahead rules enforced here:
* Macro values are aligned on their *available_on* date (observation + release lag), never on the observation date.
* Rolling statistics only use data up to and including t.
* The backtester trades on day t+1 using features from day t (see backtest/engine.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SERIES, Z_CLIP, Z_MIN_PERIODS, Z_WINDOW


def zscore(x: pd.Series, window: int = Z_WINDOW, min_periods: int = Z_MIN_PERIODS, clip: float = Z_CLIP) -> pd.Series:
    mu = x.rolling(window, min_periods=min_periods).mean()
    sd = x.rolling(window, min_periods=min_periods).std()
    z = (x - mu) / sd.replace(0, np.nan)
    return z.clip(-clip, clip)


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close).diff()


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Annualised close-to-close volatility."""
    return log_returns(close).rolling(window, min_periods=window // 2).std() * np.sqrt(252)


def atr(df: pd.DataFrame, window: int = 20) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(window, min_periods=window // 2).mean()


def trend_score(close: pd.Series) -> pd.Series:
    """Volatility-adjusted time-series momentum, averaged over 1, 3 and 6 months.

    For each lookback L: r_L / (sigma_daily * sqrt(L)), i.e. how many standard deviations the
    price has moved. Averaging three horizons avoids depending on a single tuned lookback.
    """
    lr = log_returns(close)
    sig = lr.rolling(63, min_periods=40).std()
    parts = []
    for L in (21, 63, 126):
        parts.append((np.log(close) - np.log(close.shift(L))) / (sig * np.sqrt(L)))
    return pd.concat(parts, axis=1).mean(axis=1).clip(-Z_CLIP, Z_CLIP)


def risk_adj_return(close: pd.Series, L: int = 60) -> pd.Series:
    lr = log_returns(close)
    sig = lr.rolling(126, min_periods=60).std()
    return ((np.log(close) - np.log(close.shift(L))) / (sig * np.sqrt(L))).clip(-Z_CLIP, Z_CLIP)


def align_point_in_time(series: pd.Series, lag_days: int, calendar: pd.DatetimeIndex) -> pd.Series:
    """Value known on each calendar date = latest observation whose available_on <= date."""
    s = series.dropna().sort_index()
    if s.empty:
        return pd.Series(np.nan, index=calendar, name=series.name)
    avail = pd.DataFrame({"available_on": s.index + pd.Timedelta(days=lag_days), "value": s.values})
    avail = avail.sort_values("available_on")
    cal = pd.DataFrame({"date": calendar})
    merged = pd.merge_asof(cal, avail, left_on="date", right_on="available_on", direction="backward")
    out = pd.Series(merged["value"].values, index=calendar, name=series.name)
    # Do not forward-fill forever: a daily series older than 10 days counts as missing.
    age = (calendar.to_series() - pd.Series(merged["available_on"].values, index=calendar)).dt.days
    freq = SERIES[series.name].frequency if series.name in SERIES else "daily"
    limit = {"daily": 10, "weekly": 21, "monthly": 100}.get(freq, 30)
    return out.where(age <= limit)


def build_panel(prices: dict[str, pd.DataFrame], macro: dict[str, pd.Series]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Return (macro_panel, prices_aligned).

    The calendar is the union of trading dates across instruments (weekdays). Prices are not
    forward-filled across more than 3 days; macro is aligned point-in-time.
    """
    cal = sorted(set().union(*[set(df.index) for df in prices.values()]))
    calendar = pd.DatetimeIndex(cal)
    calendar = calendar[calendar.dayofweek < 5]
    aligned = {s: df.reindex(calendar).ffill(limit=3) for s, df in prices.items()}
    cols = {}
    for sid, s in macro.items():
        lag = SERIES[sid].lag_days if sid in SERIES else 1
        s = s.copy()
        s.name = sid
        cols[sid] = align_point_in_time(s, lag, calendar)
    panel = pd.DataFrame(cols, index=calendar)
    # Derived macro features
    if {"US2Y", "JP2Y"} <= set(panel):
        panel["US_JP_2Y"] = panel["US2Y"] - panel["JP2Y"]
    if {"US2Y", "EU2Y"} <= set(panel):
        panel["EU_US_2Y"] = panel["EU2Y"] - panel["US2Y"]
    if {"US2Y", "AU2Y"} <= set(panel):
        panel["AU_US_2Y"] = panel["AU2Y"] - panel["US2Y"]
    if {"US2Y", "CA2Y"} <= set(panel):
        panel["US_CA_2Y"] = panel["US2Y"] - panel["CA2Y"]
    if "US_CPI" in panel:
        # YoY computed on the observation series then aligned, to avoid mixing availability dates
        cpi = macro["US_CPI"].sort_index()
        yoy = (cpi / cpi.shift(12) - 1) * 100
        yoy.name = "US_CPI"
        panel["US_CPI_YOY"] = align_point_in_time(yoy, SERIES["US_CPI"].lag_days, calendar)
    if {"WTI_C1", "WTI_C2"} <= set(panel):
        panel["WTI_ROLL_YIELD"] = (panel["WTI_C1"] / panel["WTI_C2"] - 1) * 100 * 12  # annualised, + = backwardation
    if {"WTI_C1", "WTI_C4"} <= set(panel):
        panel["WTI_C1_C4"] = panel["WTI_C1"] - panel["WTI_C4"]
    if "US_CRUDE_STOCKS" in macro:
        st = macro["US_CRUDE_STOCKS"].sort_index()
        # deviation of inventories from same week a year earlier (52 weeks), in %
        dev = (st / st.shift(52) - 1) * 100
        dev.name = "US_CRUDE_STOCKS"
        panel["CRUDE_STOCKS_YOY"] = align_point_in_time(dev, SERIES["US_CRUDE_STOCKS"].lag_days, calendar)
    return panel, aligned
