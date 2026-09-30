"""End-to-end pipeline run against a local JSONL sink with synthetic inputs and a fake broker."""
import json

import pandas as pd

from orion import pipeline
from orion.agent import trader
from tests.conftest import make_macro, make_prices


class FakeOanda:
    def __init__(self):
        self.orders = []
        self.pos = {}

    def summary(self):
        return {"currency": "USD", "NAV": "100000", "balance": "100000", "unrealizedPL": "0", "marginUsed": "0"}

    def instruments(self, syms):
        return {s: {"tradeUnitsPrecision": 0, "displayPrecision": 5} for s in syms}

    def prices(self, syms):
        px = make_prices()
        return {s: {"mid": float(px[s]["close"].iloc[-1]), "bid": 0, "ask": 0, "tradeable": True} for s in syms}

    def open_positions(self):
        return self.pos

    def open_trades(self):
        return []

    def market_order(self, sym, units, stop, tag):
        self.orders.append((sym, units, stop))
        return {"orderFillTransaction": {"orderID": "1", "price": "1.0"}}

    def close_position(self, sym, units):
        return {"longOrderFillTransaction": {"orderID": "2", "price": "1.0"}}


def test_daily_and_backtest(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_OUT_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    prices = make_prices()
    # make data look current so staleness checks pass
    shift = pd.Timestamp.now().normalize() - prices["USD_JPY"].index[-1]
    prices = {s: df.set_axis(df.index + shift) for s, df in prices.items()}
    prices = {s: df[df.index.dayofweek < 5] for s, df in prices.items()}
    macro = {k: v.set_axis(v.index + shift) for k, v in make_macro().items()}
    monkeypatch.setattr(pipeline, "fetch_all_prices", lambda syms, start: prices)
    monkeypatch.setattr(pipeline.macro_src, "fetch_all_macro", lambda start: macro)
    fake = FakeOanda()
    monkeypatch.setattr(trader, "Oanda", lambda: fake)

    assert pipeline.main(["seed"]) == 0
    assert pipeline.main(["daily", "--full"]) == 0
    files = {p.name for p in tmp_path.iterdir()}
    for t in ("signals.jsonl", "regimes.jsonl", "market_snapshots.jsonl", "journal.jsonl", "orders.jsonl",
              "equity_snapshots.jsonl", "performance_public.jsonl", "market_index_public.jsonl", "prices_daily.jsonl"):
        assert t in files, t
    orders = [json.loads(l) for l in open(tmp_path / "orders.jsonl")]
    assert all(o["status"] == "dry_run" for o in orders)   # trading disabled by default
    assert fake.orders == []
    perf = [json.loads(l) for l in open(tmp_path / "performance_public.jsonl")]
    assert set(perf[0]) == {"date", "nav_index", "drawdown"}
    snap = json.loads(open(tmp_path / "market_snapshots.jsonl").readline())
    assert "close" not in json.dumps(snap["what_changed"]["markets"])

    assert pipeline.main(["backtest"]) == 0
    runs = [json.loads(l) for l in open(tmp_path / "backtest_runs.jsonl")]
    assert runs[-1]["metrics_out_of_sample"]


def test_agent_live_sends_orders(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_OUT_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setitem(trader.DEFAULT_CFG, "trading_enabled", True)
    monkeypatch.setitem(trader.DEFAULT_CFG, "entry_threshold", 0.0)   # force entries on synthetic data
    fake = FakeOanda()
    monkeypatch.setattr(trader, "Oanda", lambda: fake)
    from orion.db import DB
    prices, macro = make_prices(), make_macro()
    panel, aligned, frames, regime = pipeline.compute(prices, macro)
    trader.run(frames, aligned, regime, panel.index[-1], DB(), log=lambda *a: None)
    assert fake.orders, "expected orders in live mode"
    for sym, units, stop in fake.orders:
        assert stop is not None and float(units) == int(units)


def test_smoketest_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_OUT_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    class Broker(FakeOanda):
        def prices(self, syms):
            return {"EUR_USD": {"mid": 1.1, "bid": 1.1, "ask": 1.1, "tradeable": True}}
        def market_order(self, sym, units, stop, tag):
            self.pos = {sym: {"units": units}}
            self.trades = [{"instrument": sym, "stopLossOrder": {"price": stop}}]
            return {"orderFillTransaction": {"price": "1.1"}}
        def open_trades(self):
            return getattr(self, "trades", [])
        def close_position(self, sym, units):
            self.pos, self.trades = {}, []
            return {}

    b = Broker()
    import orion.ingestion.oanda as oa
    monkeypatch.setattr(oa, "Oanda", lambda: b)
    assert pipeline.main(["smoketest"]) == 0
    assert b.pos == {}
