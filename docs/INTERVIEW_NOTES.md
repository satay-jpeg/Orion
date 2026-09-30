# Interview talking points

**Why these seven markets?** Each has a different dominant driver:
* USD/JPY: rate differential and carry
* EUR/USD: policy divergence
* AUD/USD: China and metals
* USD/CAD: oil
* Gold: real yields
* Brent: the physical balance and term structure
* Copper: global manufacturing

**Why equal weights?** With about 15 years of daily data, a handful of correlated components and regime shifts, fitted weights mostly fit noise. The backtest page publishes each component's IC so the choice can be challenged with evidence rather than assumed.

**How is look-ahead bias avoided?**
* Release-lag `available_on` dates on every macro series.
* Next-day execution in the backtest.
* A unit test that appends future data and asserts that no past signal changes.
* The known remaining gap is revised vs real-time macro vintages (fix: ALFRED).

**How is overfitting avoided?**
* Economic rationale is chosen before any testing.
* Only two parameters are tuned, over six combinations.
* Parameters are re-chosen year by year on an expanding window.
* A 12-month holdout is evaluated once.
* In-sample results are labelled as optimistic.

**What happens when it's wrong?** Every position has a pre-defined signal invalidation (the composite crosses zero) and a price invalidation (k × ATR stop). Size is set so the stop costs 0.5% of NAV. Beyond that, a portfolio circuit breaker applies.

**Why a cross-asset exposure view?** Long USD/JPY, short EUR/USD and short gold look like three trades, but all three are long USD. Decomposing positions into currency legs shows the real bet.

**Why not an LSTM or Transformer?** The goal is a signal you can explain to a risk manager and that keeps working when regimes change. Complexity without interpretability is hard to size or to switch off.

**Data licensing.** Proprietary series (ICE DXY, ISM/S&P PMIs, ICE Brent curve, LME stocks) were replaced by public proxies. Raw OANDA prices are kept private.

**Biggest limitation?** Historical relationships break. BoJ yield-curve control and 2022 energy markets are examples. The regime and analogue pages exist to show when the current environment looks unlike the training data.
