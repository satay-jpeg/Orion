import { Fragment } from "react";
import { isNum } from "@/lib/format";

const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

/** Monthly returns as a year x month grid. Diverging blue/red with a neutral midpoint; values in the title tooltip. */
export default function HeatGrid({ data }: { data: { month: string; return: number }[] }) {
  if (!data.length) return <div className="empty">No out-of-sample months yet.</div>;
  const byYear = new Map<string, Map<number, number>>();
  data.forEach(({ month, return: r }) => {
    const [y, m] = month.split("-");
    if (!byYear.has(y)) byYear.set(y, new Map());
    byYear.get(y)!.set(+m - 1, r);
  });
  const cap = Math.max(0.01, ...data.map((d) => Math.abs(d.return)).sort((a, b) => a - b).slice(0, Math.ceil(data.length * 0.95)));
  const color = (r: number) => {
    const a = Math.min(1, Math.abs(r) / cap);
    const base = r >= 0 ? "57,135,229" : "230,103,103";
    return `rgba(${base},${(0.15 + 0.75 * a).toFixed(2)})`;
  };
  return (
    <div>
      <div className="heat" role="table" aria-label="Monthly out-of-sample returns">
        <span />
        {MONTHS.map((m, i) => <span key={i} className="h">{m}</span>)}
        {[...byYear.entries()].map(([y, ms]) => (
          <Fragment key={y}>
            <span className="y">{y}</span>
            {MONTHS.map((_, i) => {
              const r = ms.get(i);
              return (
                <span key={y + i} className="c" role="cell"
                  title={isNum(r) ? `${y}-${String(i + 1).padStart(2, "0")}: ${(r * 100).toFixed(2)}%` : "no data"}
                  style={isNum(r) ? { background: color(r) } : undefined} />
              );
            })}
          </Fragment>
        ))}
      </div>
      <div className="legend" style={{ marginTop: 10 }}>
        <span><i style={{ background: "var(--neg)", height: 8, width: 8 }} />loss</span>
        <span><i style={{ background: "var(--pos)", height: 8, width: 8 }} />gain</span>
        <span className="muted">hover a cell for the value</span>
      </div>
    </div>
  );
}
