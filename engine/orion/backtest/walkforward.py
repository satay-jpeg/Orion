"""Walk-forward evaluation with a final untouched holdout.

* Signals are computed once with causal rolling windows, so they contain no fitted parameters.
* The only tuned parameters are the entry threshold and the stop multiple, chosen from a
  deliberately tiny grid (6 combinations) by in-sample Sharpe on an expanding training window.
* Each calendar year after MIN_TRAIN_YEARS is traded with parameters chosen on data before it.
* The last HOLDOUT_DAYS are never used for selection; they are evaluated once with the parameters
  chosen on all pre-holdout data.
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..config import HOLDOUT_DAYS, MIN_TRAIN_YEARS, StrategyParams
from .engine import run_portfolio
from .metrics import drawdown, monthly_returns, performance


def _grid(p: StrategyParams):
    keys = list(p.grid)
    for vals in itertools.product(*[p.grid[k] for k in keys]):
        yield replace(p, **dict(zip(keys, vals)))


def _select(prices, signals, macro, base: StrategyParams, start, end) -> tuple[StrategyParams, list[dict]]:
    scores = []
    best, best_s = base, -np.inf
    for cand in _grid(base):
        res = run_portfolio(prices, signals, cand, macro, start, end)
        s = res["metrics"].get("sharpe") or -np.inf
        scores.append({"entry_threshold": cand.entry_threshold, "stop_atr_multiple": cand.stop_atr_multiple, "sharpe": s})
        if s > best_s:
            best, best_s = cand, s
    return best, scores


def component_ic(signal_frames: dict[str, pd.DataFrame], prices: dict[str, pd.DataFrame], split: pd.Timestamp,
                 horizon: int = 20) -> dict:
    """Spearman rank IC of each component vs forward `horizon`-day return, before and after `split`.

    Sampled every `horizon` days to reduce overlap.
    """
    out = {}
    for sym, f in signal_frames.items():
        fwd = np.log(prices[sym]["close"]).shift(-horizon) - np.log(prices[sym]["close"])
        res = {}
        for col in f.columns:
            if col == "completeness":
                continue
            d = pd.concat([f[col], fwd], axis=1, keys=["x", "y"]).dropna().iloc[::horizon]
            pre, post = d[d.index < split], d[d.index >= split]
            row = {}
            for nm, part in (("pre_holdout", pre), ("holdout", post)):
                if len(part) >= 8:
                    ic, pv = spearmanr(part["x"], part["y"])
                    row[nm] = {"ic": round(float(ic), 3), "p_value": round(float(pv), 3), "n": int(len(part))}
            res[col] = row
        out[sym] = res
    return out


def walk_forward(prices, signal_frames: dict[str, pd.DataFrame], macro, base: StrategyParams | None = None,
                 log=print) -> dict:
    base = base or StrategyParams()
    signals = {s: f["composite"] for s, f in signal_frames.items()}
    first_valid = max(f["composite"].first_valid_index() for f in signal_frames.values() if f["composite"].notna().any())
    last = min(df.index[-1] for df in prices.values())
    holdout_start = last - pd.Timedelta(days=HOLDOUT_DAYS)
    years = list(range(first_valid.year + MIN_TRAIN_YEARS, holdout_start.year + 1))

    windows, oos_parts = [], []
    for y in years:
        train_end = pd.Timestamp(f"{y - 1}-12-31")
        test_start = pd.Timestamp(f"{y}-01-01")
        test_end = min(pd.Timestamp(f"{y}-12-31"), holdout_start - pd.Timedelta(days=1))
        if test_start >= test_end:
            continue
        chosen, grid = _select(prices, signals, macro, base, first_valid, train_end)
        res = run_portfolio(prices, signals, chosen, macro, test_start, test_end)
        oos_parts.append(res)
        windows.append({"train": [str(first_valid.date()), str(train_end.date())],
                        "test": [str(test_start.date()), str(test_end.date())],
                        "chosen": {"entry_threshold": chosen.entry_threshold, "stop_atr_multiple": chosen.stop_atr_multiple},
                        "grid": grid, "test_metrics": res["metrics"]})
        log(f"  WF {y}: entry={chosen.entry_threshold} stop={chosen.stop_atr_multiple} "
            f"test sharpe={res['metrics'].get('sharpe')}")

    oos_ret = pd.concat([r["returns"] for r in oos_parts]) if oos_parts else pd.Series(dtype=float)
    oos_w = pd.concat([r["weights"] for r in oos_parts]) if oos_parts else pd.DataFrame()
    oos_tr = pd.concat([r["trades"] for r in oos_parts if len(r["trades"])], ignore_index=True) if oos_parts else pd.DataFrame()

    final, _ = _select(prices, signals, macro, base, first_valid, holdout_start - pd.Timedelta(days=1))
    ins = run_portfolio(prices, signals, final, macro, first_valid, holdout_start - pd.Timedelta(days=1))
    hold = run_portfolio(prices, signals, final, macro, holdout_start, last)

    def series(ret, seg):
        eq = (1 + ret).cumprod()
        return pd.DataFrame({"date": ret.index, "segment": seg, "equity": eq.values, "drawdown": drawdown(eq).values})

    per_inst = {}
    for sym in ins["by_instrument"].columns:
        per_inst[sym] = {
            "in_sample": performance(ins["by_instrument"][sym]),
            "out_of_sample": performance(pd.concat([r["by_instrument"][sym] for r in oos_parts])) if oos_parts else {},
        }

    return {
        "config": {"base_params": ins["params"], "final_params": {"entry_threshold": final.entry_threshold,
                   "stop_atr_multiple": final.stop_atr_multiple}, "holdout_start": str(holdout_start.date()),
                   "first_signal_date": str(first_valid.date()), "grid": base.grid},
        "metrics_in_sample": ins["metrics"],
        "metrics_out_of_sample": performance(oos_ret, oos_tr, oos_w) if len(oos_ret) else {},
        "metrics_holdout": hold["metrics"],
        "walk_forward": {"windows": windows, "monthly_oos": monthly_returns(oos_ret) if len(oos_ret) else []},
        "diagnostics": {"component_ic_20d": component_ic(signal_frames, prices, holdout_start),
                        "note": "In-sample metrics use parameters selected on the same data and are optimistic. "
                                "Judge the strategy on out-of-sample and holdout."},
        "per_instrument": per_inst,
        "series": pd.concat([series(ins["returns"], "in_sample"), series(oos_ret, "out_of_sample"),
                             series(hold["returns"], "holdout")], ignore_index=True),
        "trades": pd.concat([t.assign(segment=seg) for t, seg in ((ins["trades"], "in_sample"), (oos_tr, "out_of_sample"),
                             (hold["trades"], "holdout")) if len(t)], ignore_index=True),
    }
