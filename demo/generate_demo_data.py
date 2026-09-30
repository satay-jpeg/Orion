"""Generate SYNTHETIC demo data by running the real ORION pipeline on simulated markets.

Nothing here is real market data. It exists so you can see every page of the site locally
without any accounts. Output: demo/data/*.jsonl (read by demo/mock_supabase.py).
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data"
ENGINE = HERE.parent / "engine"
sys.path.insert(0, str(ENGINE))
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
os.environ["ORION_OUT_DIR"] = str(OUT)
for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ.pop(k, None)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from orion import pipeline  # noqa: E402
from orion.agent import trader  # noqa: E402
from tests.conftest import make_macro, make_prices  # noqa: E402

print("Simulating 14 years of synthetic markets and macro data...")
prices = make_prices(3600, seed=7)
macro = make_macro(3600, seed=3)
end = pd.Timestamp.now().normalize() - pd.tseries.offsets.BDay(1)
shift = end - prices["USD_JPY"].index[-1]
prices = {s: df.set_axis(df.index + shift) for s, df in prices.items()}
prices = {s: df[df.index.dayofweek < 5] for s, df in prices.items()}
macro = {k: v.set_axis(v.index + shift) for k, v in macro.items()}
last_px = {s: float(df["close"].iloc[-1]) for s, df in prices.items()}


class DemoBroker:
    """Stands in for the OANDA practice account."""
    def summary(self):
        return {"currency": "USD", "NAV": "105900", "balance": "105600", "unrealizedPL": "300", "marginUsed": "3100"}
    def instruments(self, syms):
        return {s: {"tradeUnitsPrecision": 0, "displayPrecision": 5} for s in syms}
    def prices(self, syms):
        return {s: {"mid": last_px[s], "bid": last_px[s], "ask": last_px[s], "tradeable": True} for s in syms if s in last_px}
    def open_positions(self):
        return {}
    def open_trades(self):
        return []
    def market_order(self, sym, units, stop, tag):
        return {"orderFillTransaction": {"orderID": "demo", "price": str(last_px[sym])}}
    def close_position(self, sym, units):
        return {"longOrderFillTransaction": {"orderID": "demo", "price": str(last_px[sym])}}


pipeline.fetch_all_prices = lambda syms, start: prices
pipeline.macro_src.fetch_all_macro = lambda start: macro
trader.Oanda = lambda: DemoBroker()
trader.DEFAULT_CFG["trading_enabled"] = True

pipeline.main(["seed"])
pipeline.main(["daily", "--full"])
print("Running the walk-forward backtest (takes a minute)...")
pipeline.main(["backtest"])

# A few months of paper-portfolio history so the performance and admin pages have something to show
rng = np.random.default_rng(2)
nav, peak, eq, perf = 100000.0, 100000.0, [], []
days = pd.bdate_range(end - pd.Timedelta(days=120), end)
for d in days:
    nav *= 1 + rng.normal(0.0004, 0.004)
    peak = max(peak, nav)
    eq.append({"date": str(d.date()), "nav": nav, "balance": nav, "unrealized_pl": float(rng.normal(0, 300)),
               "margin_used": 3100, "gross_exposure": 1.4, "portfolio_vol": 0.061, "drawdown": nav / peak - 1,
               "currency_exposure": {"USD": 0.9, "JPY": -0.6, "XAU": 0.3, "EUR": -0.4, "BCO": 0.2},
               "risk": {"correlation": {"USD_JPY": {"USD_JPY": 1, "EUR_USD": -0.42, "XAU_USD": -0.18},
                                        "EUR_USD": {"USD_JPY": -0.42, "EUR_USD": 1, "XAU_USD": 0.35},
                                        "XAU_USD": {"USD_JPY": -0.18, "EUR_USD": 0.35, "XAU_USD": 1}},
                        "risk_contribution": {"USD_JPY": 0.46, "EUR_USD": 0.31, "XAU_USD": 0.23},
                        "diversification_ratio": 1.34}})
    perf.append({"date": str(d.date()), "nav_index": nav / 1000, "drawdown": nav / peak - 1})
d = str(days[-1].date())
pos = [
    {"date": d, "symbol": "USD_JPY", "units": 62000, "avg_price": last_px["USD_JPY"] * 0.99, "unrealized_pl": 840, "notional_usd": 62000, "weight": 0.62},
    {"date": d, "symbol": "EUR_USD", "units": -40000, "avg_price": last_px["EUR_USD"] * 1.004, "unrealized_pl": -210, "notional_usd": -46800, "weight": -0.47},
    {"date": d, "symbol": "XAU_USD", "units": 9, "avg_price": last_px["XAU_USD"] * 0.97, "unrealized_pl": 1320, "notional_usd": 33000, "weight": 0.33},
]


def write(name, rows):
    with open(OUT / f"{name}.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows))


write("equity_snapshots", eq)
write("performance_public", perf)
write("positions_snapshot", pos)
write("agent_config", [{"id": 1, **trader.DEFAULT_CFG, "trading_enabled": False, "halted_reason": None}])
now = pd.Timestamp.now(tz="UTC")
write("pipeline_runs", [{"kind": "daily", "status": "success", "started_at": (now - pd.Timedelta(minutes=5)).isoformat(),
                         "finished_at": now.isoformat(), "freshness": {}}])
print(f"\nDemo data written to {OUT}")
