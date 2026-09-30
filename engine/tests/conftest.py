"""Synthetic fixtures. Used ONLY for unit tests of the mechanics; never written to the database."""
import numpy as np
import pandas as pd
import pytest

from orion.config import INSTRUMENTS

START_PX = {"USD_JPY": 110.0, "EUR_USD": 1.15, "AUD_USD": 0.75, "USD_CAD": 1.30, "XAU_USD": 1500.0,
            "BCO_USD": 70.0, "XCU_USD": 3.5}


def make_prices(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", periods=n)
    out = {}
    for k, sym in enumerate(INSTRUMENTS):
        r = rng.normal(0, 0.007, n)
        close = START_PX[sym] * np.exp(np.cumsum(r))
        open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.001, n))
        hi = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
        lo = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
        out[sym] = pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close, "volume": 1}, index=idx)
    return out


def make_macro(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", periods=n)
    walk = lambda lvl, sd: pd.Series(lvl + np.cumsum(rng.normal(0, sd, n)), index=idx)
    m = {"US2Y": walk(2, .03), "US10Y": walk(3, .03), "US10Y_REAL": walk(1, .03), "US10Y_BE": walk(2, .01),
         "VIX": walk(18, .5).clip(9, 80), "USD_BROAD": walk(110, .2), "JP2Y": walk(0, .005), "EU2Y": walk(0.5, .02),
         "AU2Y": walk(2, .03), "CA2Y": walk(1.5, .03), "WTI_C1": walk(70, 1).clip(20), "WTI_C2": walk(70, 1).clip(20),
         "WTI_C4": walk(70, 1).clip(20)}
    months = pd.date_range("2012-01-01", periods=n // 21, freq="MS")
    m["CFNAI_MA3"] = pd.Series(rng.normal(0, .4, len(months)), index=months)
    m["US_CPI"] = pd.Series(230 * np.exp(np.cumsum(rng.normal(.002, .002, len(months)))), index=months)
    weeks = pd.date_range("2012-01-06", periods=n // 5, freq="W-FRI")
    m["US_CRUDE_STOCKS"] = pd.Series(450000 + np.cumsum(rng.normal(0, 2000, len(weeks))), index=weeks)
    for k, v in m.items():
        v.name = k
    return m


@pytest.fixture(scope="session")
def data():
    return make_prices(), make_macro()
