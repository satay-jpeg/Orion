import RegimeStrip from "@/components/RegimeStrip";
import SplitFlap from "@/components/SplitFlap";
import { latestSnapshot, regimeHistory } from "@/lib/data";
import { INSTRUMENT_ORDER, NAMES, isNum, pp } from "@/lib/format";

export const revalidate = 600;

const RULES: [string, string][] = [
  ["Growth", "Chicago Fed National Activity Index, 3-month average: Strong > +0.20, Weak < −0.35. Released ~3–4 weeks after month end; lagged 55 days."],
  ["Inflation", "3-month change in US CPI YoY: Rising > +0.25pp, Falling < −0.25pp. Lagged 45 days for release timing."],
  ["Risk", "VIX z-score vs its trailing 1-year distribution: Risk-off > +1.0, Risk-on < −0.5."],
  ["USD", "60-day log change in the Fed's broad dollar index, as a z-score: Strong > +0.5, Weak < −0.5."],
  ["Volatility", "Average percentile of 20-day realised volatility across the 7 markets vs 3 years: High > 80th, Low < 25th."],
];

export default async function Regime() {
  const [rows, snap] = await Promise.all([regimeHistory(3650), latestSnapshot()]);
  const cur = rows.at(-1);
  const an = snap?.analogues;
  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Market regime</h1>
          <p>Five interpretable dimensions, each from one documented rule on point-in-time data. Thresholds are round numbers fixed in advance, not optimised.</p>
        </div>
      </div>
      <section className="board cols-12">
        <div className="panel span-12">
          <h2>Now</h2>
          <SplitFlap text={cur?.label ?? "NO DATA"} />
        </div>
        <div className="panel span-12">
          <h2>Ten-year history (weekly)</h2>
          <RegimeStrip rows={rows} />
        </div>
        <div className="panel span-5">
          <h2>Classification rules</h2>
          <table className="data"><tbody>
            {RULES.map(([k, v]) => (
              <tr key={k}><td style={{ verticalAlign: "top" }}>{k}</td><td style={{ whiteSpace: "normal" }} className="ink2">{v}</td></tr>
            ))}
          </tbody></table>
        </div>
        <div className="panel span-7">
          <h2>Historical analogues</h2>
          {an?.episodes?.length ? (
            <>
              <p className="small ink2" style={{ marginTop: 0 }}>
                {an.matching_days} past trading days matched at least {an.min_match} of {an.dimensions_used?.length ?? 5} dimensions
                (excluding the last 90 days). Recent episodes:
              </p>
              <div className="small mono" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
                {an.episodes.slice(-8).map((e: any) => <span className="chip" key={e.start}>{e.start} → {e.end}</span>)}
              </div>
              <div className="tablewrap">
                <table className="data">
                  <thead><tr><th>Market</th><th className="n">5d median</th><th className="n">20d median</th><th className="n">20d hit rate</th><th className="n">60d median</th><th className="n">60d IQR</th></tr></thead>
                  <tbody>
                    {INSTRUMENT_ORDER.map((s) => {
                      const f = an.forward?.[s] ?? {};
                      return (
                        <tr key={s}>
                          <td>{NAMES[s]}</td>
                          <td className="n">{pp(f["5d"]?.median, 2)}</td>
                          <td className="n">{pp(f["20d"]?.median, 2)}</td>
                          <td className="n">{isNum(f["20d"]?.hit_rate) ? Math.round(f["20d"].hit_rate * 100) + "%" : "—"}</td>
                          <td className="n">{pp(f["60d"]?.median, 2)}</td>
                          <td className="n muted">{isNum(f["60d"]?.p25) ? `${f["60d"].p25.toFixed(1)} / ${f["60d"].p75.toFixed(1)}` : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="tiny muted" style={{ marginTop: 10 }}>{an.caveat} Days within an episode overlap, so the effective sample is much smaller than the day count.</p>
            </>
          ) : <div className="empty">{an?.caveat ?? "No analogues yet."}</div>}
        </div>
      </section>
    </>
  );
}
