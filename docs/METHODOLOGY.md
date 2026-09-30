# Methodology

## 1. Signal components

All components are z-scores against a trailing window, clipped at ±3, and signed so that **positive = supportive for the market as quoted**. Windows: 252 days (1 year) by default, which is long enough to be stable and short enough to adapt across regimes. Slow levels (carry, activity) use 756 days. A minimum of 126 observations is required.

| Market | Components |
|---|---|
| USD/JPY | rates: z(Δ20d US−JP 2Y) · carry: z(US−JP 2Y level, 3y) · risk: −z(Δ20d VIX) · volatility: −z(realised vol) × sign(carry) · trend |
| EUR/USD | rates: z(Δ20d EU−US 2Y) · carry · trend |
| AUD/USD | rates · carry · risk · metals: copper 60d risk-adjusted return · trend |
| USD/CAD | rates · carry · oil: −Brent 60d risk-adjusted return · trend |
| Gold | real yield: −z(Δ20d 10Y TIPS) · usd: −z(Δ20d log broad USD) · breakevens: z(Δ20d 10Y BE) · trend |
| Brent | curve: z(WTI C1/C2 roll yield) · inventories: −z(YoY crude stocks) · growth: z(CFNAI-MA3, 3y) · usd · trend |
| Copper | growth · usd · risk · trend |

**Trend** = average over L ∈ {21, 63, 126} days of log return divided by (daily σ × √L): how many standard deviations price has moved. Averaging several horizons avoids tuning one lookback.

**Composite** = weighted average of available components. Weights are equal by design (see the interview notes). If less than 60% of the weight has data, no composite is published.

## 2. Regimes

| Dimension | Rule | Source |
|---|---|---|
| Growth | CFNAI-MA3 > +0.20 Strong, < −0.35 Weak | Chicago Fed (−0.70 is their recession marker) |
| Inflation | 3-month change in CPI YoY > +0.25pp Rising, < −0.25pp Falling | BLS |
| Risk | VIX 1y z-score > +1.0 Risk-off, < −0.5 Risk-on | CBOE via FRED |
| USD | z(60d Δ log broad USD) > +0.5 Strong, < −0.5 Weak | Fed H.10 |
| Volatility | Mean percentile of 20d realised vol across markets (3y) > 80th High, < 25th Low | OANDA |

**Analogues:** past days (more than 90 days ago) sharing at least 4 of 5 states. The page reports median, IQR and hit rate of 5/20/60-day forward returns, and states that the windows overlap and are descriptive only.

## 3. Backtest rule

* Signal at the close of day *t* → orders at the **open of day t+1**.
* Enter long if composite ≥ +θ, short if ≤ −θ. Exit when the composite crosses back through 0 or the stop is hit.
* Stop = entry ∓ k × ATR(20). It fills at the stop, or at the open if the market gaps through it. A same-day stop-out is handled.
* Size: weight = risk / (k·ATR / price), with risk = 0.5% NAV, capped at 1× NAV per market. Book gross is capped at 3×, scaled pro rata.
* Costs per side: half-spread + slippage (bp): USD/JPY 0.6+0.5, EUR/USD 0.5+0.5, AUD/USD 0.75+0.5, USD/CAD 0.9+0.5, gold 1.25+1, Brent 2+1.5, copper 4+2 (assumptions; see `config.py`).
* Financing: FX earns or pays the base−quote 2Y differential (a proxy for the short-rate differential). Commodities pay the US 2Y on longs. A broker markup of 1.5%/yr applies in both directions.
* Returns use constant weights (exposure as a fraction of current NAV). This is a standard research simplification.

## 4. Validation

* **Tuned parameters:** only θ ∈ {0.25, 0.5, 0.75} and k ∈ {2, 3} (6 combinations). They are chosen by Sharpe on an expanding window ending the year before the test year.
* **Walk-forward:** each year from first signal + 4 years is traded with parameters chosen on prior data. The years are stitched into one OOS series.
* **Holdout:** the last 365 days are never used for selection. They are evaluated once with parameters chosen on all pre-holdout data.
* **Diagnostics:** Spearman IC of each component vs the forward 20-day return, sampled every 20 days, before and during the holdout.
* **Tests:** `engine/tests` check that appending future data changes no historical signal, that trades happen strictly the day after the signal, that costs reduce returns, position-sizing arithmetic, exposure decomposition and agent limits.

## 5. Agent

The same hysteresis rule as the backtest, plus live-only controls:

1. Kill switch (`trading_enabled`, default off). When off, the agent logs `dry_run` orders.
2. Circuit breaker: if drawdown from peak NAV exceeds 15%, it flattens everything and switches itself off.
3. Gross leverage cap and per-currency exposure cap. Positions are decomposed into currency legs, so long USD/JPY and short EUR/USD both count toward USD.
4. Rebalance band (25%) to limit turnover. Stops only ratchet in the favourable direction.
5. Every decision is journaled with the composite, its components, the regime and the invalidation levels.

## 6. Limitations

* Structural breaks: BoJ yield-curve control, MoF intervention and energy shocks change relationships.
* 2Y yields proxy for short rates in carry and financing. The WTI curve proxies for Brent. CFNAI proxies for global PMIs.
* Macro data is latest-vintage, not real-time vintage.
* Daily bars cannot see intraday stop sequencing beyond the high/low test.
* Correlation ≠ causation; IC with p < 0.05 across ~20 tests will produce false positives.
