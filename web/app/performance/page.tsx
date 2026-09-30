import HeatGrid from "@/components/HeatGrid";
import LineChart from "@/components/LineChart";
import { publicPerformance } from "@/lib/data";
import { num, pct, tone } from "@/lib/format";

export const revalidate = 600;

export default async function Performance() {
  const perf = await publicPerformance();
  const rets = perf.slice(1).map((p, i) => p.nav_index / perf[i].nav_index - 1);
  const n = rets.length;
  const mean = n ? rets.reduce((a, b) => a + b, 0) / n : 0;
  const sd = n > 1 ? Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)) : 0;
  const last = perf.at(-1);
  const months = new Map<string, { first: number; last: number }>();
  perf.forEach((p, i) => {
    const m = p.date.slice(0, 7);
    const prev = i > 0 ? perf[i - 1].nav_index : p.nav_index;
    if (!months.has(m)) months.set(m, { first: prev, last: p.nav_index });
    months.get(m)!.last = p.nav_index;
  });
  const monthly = [...months.entries()].map(([month, v]) => ({ month, return: v.last / v.first - 1 }));

  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Paper portfolio performance</h1>
          <p>The agent trades an OANDA practice account using the backtested rule. Shown here as an index (100 = first day) and drawdown only; positions, sizes and account values are private.</p>
        </div>
      </div>
      {perf.length < 2 ? <div className="notice">Live paper trading has not produced enough history yet.</div> : (
        <section className="board cols-12">
          <div className="panel span-12">
            <div className="figs" style={{ border: "1px solid var(--line)" }}>
              <div className="fig"><div className="caps">Return since start</div><div className={`v ${tone(last!.nav_index - 100)}`}>{pct(last!.nav_index / 100 - 1, 2)}</div><div className="s">{perf[0].date} → {last!.date}</div></div>
              <div className="fig"><div className="caps">Annualised vol</div><div className="v">{pct(sd * Math.sqrt(252), 1, false)}</div><div className="s">from daily index changes</div></div>
              <div className="fig"><div className="caps">Sharpe (rf = 0)</div><div className="v">{n > 20 ? num((mean / sd) * Math.sqrt(252), 2) : "—"}</div><div className="s">{n > 20 ? `${n} daily observations` : "needs 20+ days"}</div></div>
              <div className="fig"><div className="caps">Max drawdown</div><div className="v">{pct(Math.min(...perf.map((p) => p.drawdown)), 1, false)}</div><div className="s">current {pct(last!.drawdown, 1, false)}</div></div>
            </div>
          </div>
          <div className="panel span-8">
            <h2>Index</h2>
            <LineChart height={260} format="index" series={[{ name: "Paper portfolio (100 = start)", color: "var(--accent)", data: perf.map((p) => ({ x: p.date, y: p.nav_index })) }]} />
            <div className="gap" />
            <h2>Drawdown</h2>
            <LineChart height={130} format="pct" series={[{ name: "Drawdown", color: "var(--neg)", data: perf.map((p) => ({ x: p.date, y: p.drawdown })) }]} />
          </div>
          <div className="panel span-4">
            <h2>Monthly returns</h2>
            <HeatGrid data={monthly} />
            <p className="tiny muted" style={{ marginTop: 12 }}>Short live samples say very little about skill. Compare against the walk-forward backtest, which uses the same rule.</p>
          </div>
        </section>
      )}
    </>
  );
}
