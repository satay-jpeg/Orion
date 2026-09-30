import numpy as np
import pandas as pd
import pytest

from orion.agent.trader import DEFAULT_CFG, build_targets, desired_direction
from orion.analysis.research import scenarios, thesis, what_changed
from orion.backtest.engine import run_instrument, run_portfolio
from orion.backtest.metrics import performance
from orion.config import StrategyParams
from orion.features.core import align_point_in_time, atr, build_panel
from orion.regimes.engine import analogues, classify
from orion.risk.portfolio import currency_exposure, portfolio_risk, position_size
from orion.signals.engine import compute_all, decompose


@pytest.fixture(scope="module")
def computed(data):
    prices, macro = data
    panel, aligned = build_panel(prices, macro)
    frames = compute_all(panel, aligned)
    return panel, aligned, frames


def test_point_in_time_respects_release_lag():
    cal = pd.bdate_range("2024-01-01", "2024-03-29")
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-01", "2024-02-01"]), name="CFNAI_MA3")
    out = align_point_in_time(s, 55, cal)
    assert out.loc[:"2024-02-23"].isna().all()           # Jan obs not usable until Feb 25
    assert out.loc["2024-02-26"] == 1.0
    assert out.loc["2024-03-26"] == 1.0                  # Feb obs usable from Mar 27
    assert out.loc["2024-03-29"] == 2.0


def test_signals_have_no_lookahead(data):
    """Appending future data must not change any historical signal value."""
    prices, macro = data
    cut = prices["USD_JPY"].index[2000]
    p_short = {s: df.loc[:cut] for s, df in prices.items()}
    m_short = {k: v.loc[:cut] for k, v in macro.items()}
    pa, al = build_panel(p_short, m_short)
    short = compute_all(pa, al)
    pb, bl = build_panel(prices, macro)
    full = compute_all(pb, bl)
    for sym in short:
        a = short[sym]["composite"].dropna()
        b = full[sym]["composite"].reindex(a.index)
        assert np.allclose(a.values, b.values, equal_nan=True), sym


def test_composite_equals_sum_of_contributions(computed):
    _, _, frames = computed
    for sym, f in frames.items():
        row = f.dropna(subset=["composite"]).iloc[-1]
        dec = decompose(sym, row)
        assert abs(sum(v["contribution"] for v in dec.values()) - row["composite"]) < 0.01
        assert -3 <= row["composite"] <= 3


def test_backtest_costs_reduce_returns(computed):
    _, aligned, frames = computed
    p = StrategyParams()
    sig = frames["EUR_USD"]["composite"]
    r1, _, t1 = run_instrument("EUR_USD", aligned["EUR_USD"], sig, p)
    from orion.config import INSTRUMENTS, Instrument
    import dataclasses
    orig = INSTRUMENTS["EUR_USD"]
    INSTRUMENTS["EUR_USD"] = dataclasses.replace(orig, spread_bps=50, slippage_bps=10)
    try:
        r2, _, _ = run_instrument("EUR_USD", aligned["EUR_USD"], sig, p)
    finally:
        INSTRUMENTS["EUR_USD"] = orig
    assert len(t1) > 5
    assert r2.sum() < r1.sum()


def test_backtest_trades_on_next_day(computed):
    """A signal spike on day t can only affect positions from day t+1."""
    _, aligned, _ = computed
    px = aligned["EUR_USD"].dropna()
    sig = pd.Series(0.0, index=px.index)
    t = px.index[500]
    sig.loc[t] = 3.0
    p = StrategyParams(exit_threshold=0.0)
    r, w, trades = run_instrument("EUR_USD", px, sig, p)
    assert w.loc[:t].abs().sum() == 0
    assert trades[0]["entry_date"] == px.index[501].date()


def test_portfolio_and_metrics(computed):
    panel, aligned, frames = computed
    res = run_portfolio(aligned, {s: f["composite"] for s, f in frames.items()}, StrategyParams(), panel)
    m = res["metrics"]
    for k in ("sharpe", "max_drawdown", "cagr", "trades", "win_rate", "turnover_annual"):
        assert k in m
    assert m["max_drawdown"] <= 0
    assert res["weights"].abs().sum(axis=1).max() <= StrategyParams().max_gross_leverage * 1.5


def test_performance_known_values():
    r = pd.Series([0.01, -0.01] * 126, index=pd.bdate_range("2020-01-01", periods=252))
    m = performance(r)
    assert abs(m["sharpe"]) < 0.5
    assert m["max_drawdown"] < 0


def test_position_size_usdjpy():
    # $100k, 0.5% risk, 80 pip stop on USD/JPY at 150 -> $500 / (0.80 JPY * 1/150) = 93,750 units
    out = position_size(100_000, 0.005, 150.00, 149.20, "USD_JPY", {"USD_JPY": 150.0})
    assert abs(out["units"] - 93_750) < 1
    assert abs(out["stop_distance_pips"] - 80) < 1e-6


def test_currency_exposure_overlap():
    px = {"USD_JPY": 150.0, "EUR_USD": 1.10, "XAU_USD": 2000.0}
    exp = currency_exposure({"USD_JPY": 100_000, "EUR_USD": -50_000, "XAU_USD": 10}, px)
    assert abs(exp["USD"] - (100_000 + 55_000 - 20_000)) < 1e-6
    assert abs(exp["JPY"] + 100_000) < 1e-6
    assert abs(exp["XAU"] - 20_000) < 1e-6


def test_portfolio_risk(computed):
    _, aligned, _ = computed
    r = portfolio_risk({"EUR_USD": 1.0, "USD_JPY": 0.5}, aligned)
    assert r["portfolio_vol"] > 0
    assert abs(sum(r["risk_contribution"].values()) - 1) < 1e-6


def test_agent_hysteresis():
    assert desired_direction(0, 0.6, 0.5, 0.0) == 1
    assert desired_direction(0, 0.4, 0.5, 0.0) == 0
    assert desired_direction(1, 0.1, 0.5, 0.0) == 1      # hold until exit level
    assert desired_direction(1, -0.1, 0.5, 0.0) == 0
    assert desired_direction(1, -0.7, 0.5, 0.0) == -1
    assert desired_direction(-1, float("nan"), 0.5, 0.0) == -1


def test_agent_targets_respect_limits():
    mids = {"USD_JPY": 150.0, "EUR_USD": 1.1, "AUD_USD": 0.65, "USD_CAD": 1.35, "XAU_USD": 2000.0, "BCO_USD": 80.0, "XCU_USD": 4.5}
    scores = {s: 2.0 for s in mids}
    atrs = {"USD_JPY": 0.3, "EUR_USD": 0.001, "AUD_USD": 0.001, "USD_CAD": 0.002, "XAU_USD": 5.0, "BCO_USD": 0.5, "XCU_USD": 0.02}
    cfg = dict(DEFAULT_CFG)
    t, notes = build_targets(cfg, 100_000, mids, {}, scores, atrs)
    from orion.risk.portfolio import notional_weights
    w = notional_weights({s: x.units for s, x in t.items()}, mids, 100_000)
    assert sum(abs(v) for v in w.values()) <= cfg["max_gross_leverage"] + 1e-6
    exp = currency_exposure({s: x.units for s, x in t.items()}, mids)
    assert max(abs(v) for v in exp.values()) / 100_000 <= cfg["max_currency_exposure"] + 1e-6
    assert notes


def test_regime_and_research(computed, data):
    panel, aligned, frames = computed
    reg = classify(panel, aligned)
    asof = panel.index[-1]
    assert isinstance(reg.loc[asof, "label"], str)
    a = analogues(reg, aligned, asof)
    assert "forward" in a
    wc = what_changed(panel, aligned, frames, asof)
    assert wc["macro"] and wc["markets"] and wc["signals"]
    assert all("close" not in m for m in wc["markets"])
    th = thesis("USD_JPY", frames["USD_JPY"], aligned["USD_JPY"], reg.loc[asof], asof,
                float(atr(aligned["USD_JPY"]).iloc[-1]), 2.5)
    assert th["invalidation"]["signal"]
    sc = scenarios(panel, aligned, asof)
    up = next(s for s in sc["scenarios"] if s["id"] == "us2y_up_25")
    assert up["impact"]["USD_JPY"] > 0          # higher US yields -> USD/JPY rates component up
    assert up["impact"]["EUR_USD"] < 0


def test_walk_forward_smoke(computed):
    from orion.backtest.walkforward import walk_forward
    panel, aligned, frames = computed
    base = StrategyParams()
    base.grid = {"entry_threshold": [0.5], "stop_atr_multiple": [2.5]}
    res = walk_forward(aligned, frames, panel, base, log=lambda *a: None)
    assert res["walk_forward"]["windows"]
    segs = set(res["series"]["segment"])
    assert {"in_sample", "out_of_sample", "holdout"} <= segs
    # OOS windows never overlap the holdout
    hs = pd.Timestamp(res["config"]["holdout_start"])
    assert all(pd.Timestamp(w["test"][1]) < hs for w in res["walk_forward"]["windows"])
