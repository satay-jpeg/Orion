import Link from "next/link";
import ScoreBar from "@/components/ScoreBar";
import { latestSignals, latestSnapshot } from "@/lib/data";
import { INSTRUMENT_ORDER, NAMES, isNum, signed } from "@/lib/format";

export const revalidate = 600;

export default async function Signals() {
  const [signals, snap] = await Promise.all([latestSignals(), latestSnapshot()]);
  const by = Object.fromEntries(signals.map((s) => [s.symbol, s]));
  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Signal monitor</h1>
          <p>Each composite is the weighted average of independent components in z-units (clipped at ±3). Positive means supportive for the market as quoted. Contributions add up to the composite.</p>
        </div>
      </div>
      <section className="board cols-12">
        {INSTRUMENT_ORDER.filter((s) => by[s]).map((s) => {
          const sg = by[s];
          const th = snap?.theses?.[s];
          const comps = Object.entries(sg.components).sort((a, b) => Math.abs(b[1].contribution) - Math.abs(a[1].contribution));
          return (
            <div key={s} className="panel span-6">
              <h2><span style={{ color: "var(--ink)", letterSpacing: ".04em" }}>{NAMES[s]}</span><Link href={`/signals/${s}`}>detail →</Link></h2>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 10 }}>
                <span className="mono" style={{ fontSize: 24 }}>{signed(sg.composite)}</span>
                <span className={`chip ${sg.label === "Positive" ? "pos" : sg.label === "Negative" ? "neg" : ""}`}>{sg.label}</span>
                <span className="small muted">data completeness {Math.round((sg.completeness ?? 0) * 100)}%</span>
              </div>
              <table className="data">
                <thead><tr><th>Component</th><th className="n">z</th><th className="n">Weight</th><th className="n">Contrib.</th><th /></tr></thead>
                <tbody>
                  {comps.map(([k, c]) => (
                    <tr key={k} title={c.description}>
                      <td>{k.replace("_", " ")}</td>
                      <td className="n">{isNum(c.value) ? signed(c.value) : "n/a"}</td>
                      <td className="n">{(c.weight * 100).toFixed(0)}%</td>
                      <td className="n">{signed(c.contribution)}</td>
                      <td><ScoreBar value={c.contribution} max={1.5} width={90} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {th && <p className="small ink2" style={{ margin: "12px 0 0" }}>{th.thesis}</p>}
            </div>
          );
        })}
        {!signals.length && <div className="panel span-12"><div className="empty">No signals yet.</div></div>}
      </section>
    </>
  );
}
