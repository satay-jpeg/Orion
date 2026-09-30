import { notFound } from "next/navigation";
import LineChart from "@/components/LineChart";
import ScoreBar from "@/components/ScoreBar";
import { latestSnapshot, marketIndex, signalHistory } from "@/lib/data";
import { INSTRUMENT_ORDER, NAMES, isNum, signed } from "@/lib/format";

export const revalidate = 600;
export const dynamicParams = false;
export function generateStaticParams() { return INSTRUMENT_ORDER.map((symbol) => ({ symbol })); }

const PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"];

export default async function Instrument({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  if (!(INSTRUMENT_ORDER as readonly string[]).includes(symbol)) notFound();
  const [hist, idx, snap] = await Promise.all([signalHistory(symbol), marketIndex(symbol), latestSnapshot()]);
  const th = snap?.theses?.[symbol];
  const last = hist.at(-1);
  const compNames = last ? Object.keys(last.components) : [];
  const recent = hist.slice(-260);
  const scen = snap?.scenarios?.scenarios ?? [];

  return (
    <>
      <div className="pagehead">
        <div>
          <h1>{NAMES[symbol]}</h1>
          <p>{th?.thesis ?? "No thesis yet."}</p>
        </div>
        {last && <span className="mono" style={{ fontSize: 26 }}>{signed(last.composite)}</span>}
      </div>

      <section className="board cols-12">
        <div className="panel span-8">
          <h2>Composite signal, 4 years</h2>
          <LineChart height={230} format="score" zero yDomain={[-3, 3]}
            series={[{ name: "Composite", color: "var(--accent)", data: hist.map((h) => ({ x: h.date, y: h.composite })) }]} />
        </div>
        <div className="panel span-4">
          <h2>Decomposition today</h2>
          {last ? (
            <table className="data">
              <tbody>
                {Object.entries(last.components).map(([k, c]) => (
                  <tr key={k} title={c.description}>
                    <td>{k.replace("_", " ")}<div className="tiny muted" style={{ whiteSpace: "normal" }}>{c.description}</div></td>
                    <td className="n">{signed(c.contribution)}</td>
                    <td><ScoreBar value={c.contribution} max={1.5} width={70} /></td>
                  </tr>
                ))}
                <tr><td><b>Composite</b></td><td className="n"><b>{signed(last.composite)}</b></td><td /></tr>
              </tbody>
            </table>
          ) : <div className="empty">No data.</div>}
        </div>

        <div className="panel span-8">
          <h2>Components, last 12 months (z)</h2>
          <LineChart height={230} format="score" zero
            series={compNames.map((n, i) => ({ name: n, color: PALETTE[i % PALETTE.length],
              data: recent.filter((h) => isNum(h.components[n]?.value)).map((h) => ({ x: h.date, y: h.components[n].value as number })) }))} />
        </div>
        <div className="panel span-4">
          <h2>Trade thesis</h2>
          {th ? (
            <div className="stack small">
              <div><span className="caps">Bias</span><div style={{ fontSize: 16 }}>{th.bias}</div></div>
              <div><span className="caps">Invalidation</span>
                <ul className="ticks"><li>{th.invalidation.signal}</li>{th.invalidation.price && <li>{th.invalidation.price}</li>}</ul></div>
              <div><span className="caps">Catalysts</span><ul className="ticks">{th.catalysts.map((c: string) => <li key={c}>{c}</li>)}</ul></div>
              <div><span className="caps">Risks</span><ul className="ticks">{th.risks.map((c: string) => <li key={c}>{c}</li>)}</ul></div>
              <div><span className="caps">Horizon</span><div className="ink2">{th.horizon}</div></div>
              <div className="tiny muted">{th.disclaimer}</div>
            </div>
          ) : <div className="empty">No thesis yet.</div>}
        </div>

        <div className="panel span-8">
          <h2>Price, rebased to 100</h2>
          <LineChart height={200} format="index" series={[{ name: NAMES[symbol], color: "var(--ink-2)", data: idx.map((p) => ({ x: p.date, y: p.index_value })) }]} />
        </div>
        <div className="panel span-4">
          <h2>Scenario impact on this signal</h2>
          <table className="data"><tbody>
            {scen.map((s: any) => (
              <tr key={s.id}><td>{s.name}</td><td className="n">{signed(s.impact?.[symbol])}</td></tr>
            ))}
          </tbody></table>
        </div>
      </section>
    </>
  );
}
