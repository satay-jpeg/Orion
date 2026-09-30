import HeatGrid from "@/components/HeatGrid";
import LineChart from "@/components/LineChart";
import { latestBacktest } from "@/lib/data";
import { INSTRUMENT_ORDER, NAMES, isNum, num, pct, signed } from "@/lib/format";

export const revalidate = 3600;

const ROWS: [string, string, (v: any) => string][] = [
  ["Period", "start", (v) => v ?? "—"],
  ["Total return", "total_return", (v) => pct(v, 1)],
  ["CAGR", "cagr", (v) => pct(v, 2)],
  ["Annualised vol", "ann_vol", (v) => pct(v, 1, false)],
  ["Sharpe (rf = 0)", "sharpe", (v) => num(v, 2)],
  ["Sortino", "sortino", (v) => num(v, 2)],
  ["Max drawdown", "max_drawdown", (v) => pct(v, 1, false)],
  ["Calmar", "calmar", (v) => num(v, 2)],
  ["Trades", "trades", (v) => (isNum(v) ? String(v) : "—")],
  ["Win rate", "win_rate", (v) => pct(v, 0, false)],
  ["Profit factor", "profit_factor", (v) => num(v, 2)],
  ["Avg trade (NAV)", "avg_trade", (v) => pct(v, 2)],
  ["Avg holding (days)", "avg_holding_days", (v) => num(v, 1)],
  ["Turnover (x NAV / yr)", "turnover_annual", (v) => num(v, 1)],
  ["Avg gross leverage", "avg_gross_leverage", (v) => num(v, 2)],
];

export default async function Backtest() {
  const bt = await latestBacktest();
  if (!bt) {
    return (<><div className="pagehead"><div><h1>Backtest</h1></div></div><div className="notice">No backtest yet. Run the weekly backtest workflow once.</div></>);
  }
  const { run, series, trades } = bt;
  const seg = (s: string) => series.filter((r) => r.segment === s);
  // chain OOS and holdout into one continuous equity line for display
  const oos = seg("out_of_sample"), hold = seg("holdout");
  const lastOos = oos.at(-1)?.equity ?? 1;
  const chained = [...oos.map((r) => ({ x: r.date, y: r.equity })), ...hold.map((r) => ({ x: r.date, y: r.equity * lastOos }))];
  const ddChained = [...oos, ...hold].map((r) => ({ x: r.date, y: r.drawdown }));
  const ins = seg("in_sample").map((r) => ({ x: r.date, y: r.equity }));
  const cfg = run.config ?? {};
  const ic = run.diagnostics?.component_ic_20d ?? {};
  const created = new Date(run.created_at).toISOString().slice(0, 10);

  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Walk-forward backtest</h1>
          <p>
            The same rule the paper agent trades: enter when the composite crosses ±entry threshold, exit when it crosses back through {num(cfg.base_params?.exit_threshold, 1)}{" "}
            or an ATR stop is hit; 0.5% of NAV at risk per trade; spreads, slippage and financing charged. Parameters are re-chosen each year from a 6-point grid using
            only prior data; the final 12 months are an untouched holdout.
          </p>
        </div>
        <span className="muted small mono">run {created}</span>
      </div>

      <section className="board cols-12">
        <div className="panel span-8">
          <h2>Out-of-sample equity, then holdout</h2>
          <LineChart height={260} format="num" bands={hold.length ? [{ from: hold[0].date, to: hold.at(-1)!.date, label: "HOLDOUT" }] : []}
            series={[{ name: "Walk-forward OOS → holdout (growth of 1)", color: "var(--accent)", data: chained }]} />
          <div className="gap" />
          <h2>Drawdown</h2>
          <LineChart height={130} format="pct" series={[{ name: "Drawdown", color: "var(--neg)", data: ddChained }]} />
        </div>
        <div className="panel span-4">
          <h2>Statistics</h2>
          <table className="data">
            <thead><tr><th /><th className="n">In-sample</th><th className="n">OOS</th><th className="n">Holdout</th></tr></thead>
            <tbody>
              {ROWS.map(([label, key, f]) => (
                <tr key={key}>
                  <td>{label}</td>
                  {[run.metrics_in_sample, run.metrics_out_of_sample, run.metrics_holdout].map((m, i) => (
                    <td key={i} className="n">{key === "start" ? (m?.start ? `${m.start.slice(2, 7)}→${m.end.slice(2, 7)}` : "—") : f(m?.[key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="tiny muted" style={{ marginTop: 10 }}>In-sample uses parameters chosen on the same data and is optimistic by construction. Judge the strategy on OOS and holdout.</p>
        </div>

        <div className="panel span-6">
          <h2>Walk-forward windows</h2>
          <div className="tablewrap">
            <table className="data">
              <thead><tr><th>Test year</th><th className="n">Entry</th><th className="n">Stop ×ATR</th><th className="n">Return</th><th className="n">Sharpe</th><th className="n">Max DD</th><th className="n">Trades</th></tr></thead>
              <tbody>
                {(run.walk_forward?.windows ?? []).map((w: any) => (
                  <tr key={w.test[0]}>
                    <td className="mono">{w.test[0].slice(0, 4)}{w.test[1].slice(5) !== "12-31" ? "*" : ""}</td>
                    <td className="n">{num(w.chosen.entry_threshold, 2)}</td>
                    <td className="n">{num(w.chosen.stop_atr_multiple, 1)}</td>
                    <td className="n">{pct(w.test_metrics?.total_return, 1)}</td>
                    <td className="n">{num(w.test_metrics?.sharpe, 2)}</td>
                    <td className="n">{pct(w.test_metrics?.max_drawdown, 1, false)}</td>
                    <td className="n">{w.test_metrics?.trades ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tiny muted" style={{ marginTop: 8 }}>* partial year (ends where the holdout begins, {cfg.holdout_start}).</p>
        </div>
        <div className="panel span-6">
          <h2>Monthly returns, out-of-sample</h2>
          <HeatGrid data={run.walk_forward?.monthly_oos ?? []} />
        </div>

        <div className="panel span-7">
          <h2>Does each component predict? (20-day rank IC)</h2>
          <div className="tablewrap">
            <table className="data">
              <thead><tr><th>Market</th><th>Component</th><th className="n">IC pre-holdout</th><th className="n">p</th><th className="n">IC holdout</th><th className="n">n</th></tr></thead>
              <tbody>
                {INSTRUMENT_ORDER.flatMap((s) => Object.entries(ic[s] ?? {}).map(([c, v]: [string, any], k) => (
                  <tr key={s + c}>
                    <td>{k === 0 ? NAMES[s] : ""}</td>
                    <td className={c === "composite" ? "" : "ink2"}>{c === "composite" ? <b>composite</b> : c.replace("_", " ")}</td>
                    <td className="n" style={{ color: isNum(v.pre_holdout?.ic) && v.pre_holdout.p_value < 0.05 ? "var(--ink)" : "var(--muted)" }}>{signed(v.pre_holdout?.ic, 3)}</td>
                    <td className="n muted">{num(v.pre_holdout?.p_value, 2)}</td>
                    <td className="n">{signed(v.holdout?.ic, 3)}</td>
                    <td className="n muted">{v.pre_holdout?.n ?? "—"}</td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
          <p className="tiny muted" style={{ marginTop: 8 }}>Spearman correlation between the component and the next 20-day log return, sampled every 20 days to limit overlap. Bold ink = p &lt; 0.05. Weights are equal and are not fitted to these numbers.</p>
        </div>
        <div className="panel span-5">
          <h2>Recent trades</h2>
          <div className="tablewrap">
            <table className="data">
              <thead><tr><th>Market</th><th>Side</th><th>Entry</th><th className="n">Days</th><th className="n">NAV %</th><th>Exit</th></tr></thead>
              <tbody>
                {trades.slice(0, 18).map((t: any, i: number) => (
                  <tr key={i}>
                    <td>{NAMES[t.symbol]}</td>
                    <td>{t.direction > 0 ? "Long" : "Short"}</td>
                    <td className="mono small">{t.entry_date}</td>
                    <td className="n">{t.bars}</td>
                    <td className={`n ${t.return_pct > 0 ? "up" : "down"}`}>{pct(t.return_pct, 2)}</td>
                    <td className="muted small">{t.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel span-12">
          <h2>In-sample equity (for reference only)</h2>
          <LineChart height={160} format="num" series={[{ name: "In-sample (growth of 1)", color: "var(--muted)", data: ins }]} />
        </div>
      </section>
    </>
  );
}
