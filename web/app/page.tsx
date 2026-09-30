import Link from "next/link";
import LineChart from "@/components/LineChart";
import ScoreBar from "@/components/ScoreBar";
import RegimeStrip from "@/components/RegimeStrip";
import SplitFlap from "@/components/SplitFlap";
import { latestSignals, latestSnapshot, publicPerformance, regimeHistory } from "@/lib/data";
import { INSTRUMENT_ORDER, NAMES, arrow, isNum, num, pp, pct, signed, tone } from "@/lib/format";

export const revalidate = 600;

const DIM_LABEL: Record<string, string> = { growth: "Growth", inflation: "Inflation", risk: "Risk", usd: "USD", volatility: "Volatility" };
const DIM_INPUT: Record<string, string> = {
  growth: "CFNAI 3m avg", inflation: "Δ CPI YoY, 3m (pp)", risk: "VIX z-score (1y)", usd: "USD 60d z-score", volatility: "Avg vol percentile",
};

export default async function Overview() {
  const [snap, signals, regimes, perf] = await Promise.all([latestSnapshot(), latestSignals(), regimeHistory(400), publicPerformance()]);
  const regime = regimes.at(-1);
  let since = regimes.length - 1;
  while (since > 0 && regimes[since - 1].label === regime?.label) since--;
  const prevLabel = since > 0 ? regimes[since - 1].label : null;
  const wc = snap?.what_changed;
  const markets: Record<string, any> = Object.fromEntries((wc?.markets ?? []).map((m: any) => [m.symbol, m]));
  const sigs = Object.fromEntries(signals.map((s) => [s.symbol, s]));
  const sigChange: Record<string, any> = Object.fromEntries((wc?.signals ?? []).map((s: any) => [s.symbol, s]));
  const lastPerf = perf.at(-1);

  if (!snap && !signals.length) {
    return (
      <>
        <div className="pagehead"><div><h1>Market overview</h1><p>No data yet.</p></div></div>
        <div className="notice">The database is empty. Run the <span className="mono">daily</span> workflow once (see README) and this page fills in.</div>
      </>
    );
  }

  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Market overview</h1>
          <p>Seven liquid FX and commodity markets, scored on macro drivers. Every number decomposes into its inputs.</p>
        </div>
        <span className="muted small mono">as of {snap?.date ?? signals[0]?.date}</span>
      </div>

      <section className="board cols-12">
        <div className="panel span-8">
          <h2>Current regime <Link href="/regime">history &amp; analogues →</Link></h2>
          <div style={{ margin: "4px 0 16px" }}><SplitFlap text={regime?.label ?? "NO DATA"} /></div>
          <div className="figs" style={{ border: "1px solid var(--line)" }}>
            {Object.keys(DIM_LABEL).map((k) => (
              <div className="fig" key={k}>
                <div className="caps">{DIM_LABEL[k]}</div>
                <div className="v" style={{ fontSize: 17 }}>{(regime as any)?.[k] ?? "—"}</div>
                <div className="s">{DIM_INPUT[k]}: <span className="mono">{num(regime?.inputs?.[k], 2)}</span></div>
              </div>
            ))}
          </div>
          <p className="small ink2" style={{ margin: "14px 0 12px" }}>
            {regime ? <>In this regime for <span className="mono">{regimes.length - since}</span> trading days (since <span className="mono">{regimes[since]?.date}</span>){prevLabel ? <>, previously <span className="mono">{prevLabel}</span></> : null}.</> : null}
          </p>
          <div className="caps" style={{ marginBottom: 6 }}>Last 12 months</div>
          <RegimeStrip rows={regimes.slice(-260)} compact />
        </div>
        <div className="panel span-4">
          <h2>What changed this week</h2>
          {wc?.headlines?.length ? (
            <ul className="plain">{wc.headlines.map((h: string) => <li key={h}>{h}</li>)}</ul>
          ) : <div className="empty">No large moves this week.</div>}
          <p className="tiny muted" style={{ marginTop: 10 }}>Generated from calculated changes with fixed templates, not written by a model.</p>
        </div>
      </section>

      <div className="gap" />
      <section className="cards" style={{ border: "1px solid var(--line)" }}>
        {INSTRUMENT_ORDER.filter((s) => sigs[s]).map((s) => {
          const sg = sigs[s];
          const m = markets[s];
          const ch = sigChange[s];
          const posPct = 50 + (Math.max(-1.5, Math.min(1.5, sg.composite)) / 1.5) * 50;
          return (
            <Link key={s} href={`/signals/${s}`} className="card">
              <div className="row">
                <span className="sym">{NAMES[s]}</span>
                <span className={`chip ${sg.label === "Positive" ? "pos" : sg.label === "Negative" ? "neg" : ""}`}>{sg.label}</span>
              </div>
              <div className="row">
                <span className="score">{signed(sg.composite)}</span>
                <span className="small muted mono">1w {signed(ch?.change_1w)}</span>
              </div>
              <div className="rail" aria-hidden>
                <em style={{ left: "50%" }} /><i style={{ left: `${posPct}%`, background: sg.composite >= 0 ? "var(--pos)" : "var(--neg)" }} />
              </div>
              <div className="row small">
                <span className={tone(m?.["1d"])}>{arrow(m?.["1d"])} {pp(m?.["1d"], 2)} <span className="muted">1d</span></span>
                <span className={tone(m?.["1m"])}>{pp(m?.["1m"], 1)} <span className="muted">1m</span></span>
              </div>
            </Link>
          );
        })}
      </section>

      <div className="gap" />
      <section className="board cols-12">
        <div className="panel span-7">
          <h2>Markets &amp; signals <Link href="/signals">all components →</Link></h2>
          <div className="tablewrap">
            <table className="data">
              <thead><tr><th>Market</th><th className="n">1d</th><th className="n">1w</th><th className="n">1m</th><th className="n">3y pctile</th><th className="n">Score</th><th>−1.5 … +1.5</th></tr></thead>
              <tbody>
                {INSTRUMENT_ORDER.map((s) => {
                  const m = markets[s]; const sg = sigs[s];
                  return (
                    <tr key={s}>
                      <td><Link href={`/signals/${s}`}>{NAMES[s]}</Link></td>
                      <td className={`n ${tone(m?.["1d"])}`}>{pp(m?.["1d"], 2)}</td>
                      <td className={`n ${tone(m?.["1w"])}`}>{pp(m?.["1w"], 2)}</td>
                      <td className={`n ${tone(m?.["1m"])}`}>{pp(m?.["1m"], 1)}</td>
                      <td className="n">{isNum(m?.percentile_3y) ? Math.round(m.percentile_3y * 100) : "—"}</td>
                      <td className="n">{signed(sg?.composite)}</td>
                      <td><ScoreBar value={sg?.composite} max={1.5} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="tiny muted" style={{ marginTop: 10 }}>Price levels are not published here (OANDA data licence); changes and percentiles are derived analytics.</p>
        </div>
        <div className="panel span-5">
          <h2>Macro snapshot</h2>
          <div className="tablewrap">
            <table className="data">
              <thead><tr><th>Series</th><th className="n">Level</th><th className="n">1w</th><th className="n">1m</th><th className="n">3y pct</th></tr></thead>
              <tbody>
                {(wc?.macro ?? []).map((r: any) => (
                  <tr key={r.id}>
                    <td>{r.name}</td>
                    <td className="n">{r.unit === "bp" ? r.level.toFixed(2) + "%" : num(r.level, r.id === "USD_BROAD" ? 1 : 2)}</td>
                    <td className={`n ${tone(r["1w"])}`}>{r.unit === "%" ? pp(r["1w"], 2) : num(r["1w"], r.unit === "bp" ? 0 : 1, true)}{r.unit === "bp" ? "bp" : ""}</td>
                    <td className={`n ${tone(r["1m"])}`}>{r.unit === "%" ? pp(r["1m"], 2) : num(r["1m"], r.unit === "bp" ? 0 : 1, true)}{r.unit === "bp" ? "bp" : ""}</td>
                    <td className="n">{isNum(r.percentile_3y) ? Math.round(r.percentile_3y * 100) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <div className="gap" />
      <section className="board cols-12">
        <div className="panel span-6">
          <h2>Paper portfolio (indexed) <Link href="/performance">details →</Link></h2>
          {perf.length ? (
            <>
              <div className="figs" style={{ marginBottom: 12, border: "1px solid var(--line)" }}>
                <div className="fig"><div className="caps">Since inception</div><div className={`v ${tone((lastPerf?.nav_index ?? 100) - 100)}`}>{pp((lastPerf?.nav_index ?? 100) - 100, 2)}</div></div>
                <div className="fig"><div className="caps">Drawdown</div><div className="v">{pct(lastPerf?.drawdown, 1, false)}</div></div>
                <div className="fig"><div className="caps">Days live</div><div className="v">{perf.length}</div></div>
              </div>
              <LineChart height={160} format="index" series={[{ name: "Index (100 = start)", color: "var(--accent)", data: perf.map((p) => ({ x: p.date, y: p.nav_index })) }]} />
            </>
          ) : <div className="empty">The paper portfolio has not started yet.</div>}
        </div>
        <div className="panel span-6">
          <h2>Scenario analysis: signal impact</h2>
          {snap?.scenarios?.scenarios?.length ? (
            <div className="tablewrap">
              <table className="data">
                <thead><tr><th>Shock</th>{INSTRUMENT_ORDER.map((s) => <th key={s} className="n">{NAMES[s].replace("/", "")}</th>)}</tr></thead>
                <tbody>
                  {snap.scenarios.scenarios.map((sc: any) => (
                    <tr key={sc.id}>
                      <td>{sc.name}</td>
                      {INSTRUMENT_ORDER.map((s) => {
                        const v = sc.impact?.[s];
                        return <td key={s} className="n" style={{ color: !isNum(v) || Math.abs(v) < 0.05 ? "var(--muted)" : v > 0 ? "var(--pos)" : "var(--neg)" }}>{isNum(v) && Math.abs(v) >= 0.005 ? signed(v) : "0"}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty">No scenarios yet.</div>}
          <p className="tiny muted" style={{ marginTop: 10 }}>{snap?.scenarios?.note}</p>
        </div>
      </section>
    </>
  );
}
