import { dataSources } from "@/lib/data";

export const revalidate = 86400;

export default async function Methodology() {
  const sources = await dataSources();
  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Methodology</h1>
          <p>How ORION turns data into signals, regimes, trades and risk, and what it deliberately does not claim.</p>
        </div>
      </div>
      <section className="board cols-12">
        <div className="panel span-12">
          <div className="prose">
            <h3>1. Question</h3>
            <p>For each of seven markets ORION asks four things: why this market, what is the signal, does the signal work out of sample, and how much risk should be taken. It is a research tool, not a price predictor.</p>

            <h3>2. Data and look-ahead control</h3>
            <p>Every macro series is stored with an <code>available_on</code> date equal to its observation date plus a documented release lag (1 day for daily market data, 45 days for CPI, 55 days for the Chicago Fed activity index, 5 days for weekly EIA inventories). Signals on day <i>t</i> only see values available by <i>t</i>. The backtester trades on day <i>t+1</i> using signals from the close of day <i>t</i>. A unit test appends future data and checks that no historical signal changes.</p>
            <p>Macro series are latest-vintage (revised) values from FRED and central banks, not real-time vintages. For CPI and activity indices this slightly flatters history; ALFRED vintages are a planned upgrade.</p>
            <p>Prices are OANDA mid candles aligned to the 17:00 New York close. Raw price levels stay admin-only because of OANDA's data licence; public pages show changes, percentiles and a rebased index.</p>

            <h3>3. Signals</h3>
            <p>Each component is converted to a z-score against its trailing 252-day distribution (756 days for slow carry levels), clipped at ±3, and signed so positive supports the market as quoted. Rate-differential components use the 20-day change in 2-year yield spreads; carry uses the spread level; trend is volatility-adjusted momentum averaged over 1, 3 and 6 months. The composite is an equal-weighted average of available components, and is not published when less than 60% of the component weight has data.</p>
            <p>Equal weights are a deliberate choice: with a handful of correlated inputs and about fifteen years of data, fitted weights mostly fit noise. The backtest page reports each component's rank IC so the choice can be challenged with evidence.</p>

            <h3>4. Regimes</h3>
            <p>Growth, inflation, risk, USD and volatility are classified with one rule each, using round-number thresholds fixed in advance (see the Regime page). Historical analogues are past days sharing at least four of five states; their forward returns are descriptive only.</p>

            <h3>5. Backtest</h3>
            <p>Entry when the composite crosses ±threshold, exit when it crosses back through zero or a stop at k × ATR(20) is hit. Position size risks 0.5% of NAV to the stop, capped at 1× NAV per market and 3× gross. Costs: half-spread plus slippage per side (1–8 bp depending on market), daily financing at the 2-year rate differential minus a 1.5% broker markup. Only two parameters are tuned (entry threshold and stop multiple, six combinations), re-chosen each year on an expanding window. The last twelve months are held out and evaluated once.</p>

            <h3>6. Paper trading agent</h3>
            <p>The agent runs after the New York close, applies the same rule to today's signals, applies portfolio limits (gross leverage, per-currency exposure), and sends market orders with stops to an OANDA practice account. It has a kill switch (off by default) and a drawdown circuit breaker that flattens the book and switches itself off at −15%. Every action is journaled with the full signal decomposition. No language model makes trading decisions.</p>

            <h3>7. Limitations</h3>
            <p>Relationships between rates and currencies change across regimes and central-bank interventions. 2-year yields proxy for short-rate differentials in the financing model. The WTI curve proxies for Brent term structure, and the Chicago Fed index proxies for global manufacturing PMIs (which are proprietary). Correlation is not causation, and a short live record says little about skill.</p>
          </div>
        </div>
        <div className="panel span-12" id="sources">
          <h2>Data sources and licences</h2>
          <div className="tablewrap">
            <table className="data">
              <thead><tr><th>Series</th><th>Provider</th><th>Freq.</th><th>Release lag used</th><th>Licence / attribution</th></tr></thead>
              <tbody>
                {sources.map((s: any) => (
                  <tr key={s.id}>
                    <td style={{ whiteSpace: "normal", minWidth: 200 }}><a href={s.url} rel="noopener noreferrer" target="_blank">{s.name}</a></td>
                    <td className="mono small">{s.provider}</td>
                    <td className="small">{s.frequency}</td>
                    <td className="small">{s.release_lag}</td>
                    <td className="small ink2" style={{ whiteSpace: "normal", minWidth: 260 }}>{s.license}{s.notes ? ` ${s.notes}` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!sources.length && <div className="empty">Run the seed workflow to populate the source registry.</div>}
          </div>
        </div>
      </section>
    </>
  );
}
