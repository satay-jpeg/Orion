import type { RegimeRow } from "@/lib/data";

const STATES: Record<string, [string, string, string]> = {
  // [low/negative, neutral, high/positive] labels per dimension
  growth: ["Weak", "Neutral", "Strong"],
  inflation: ["Falling", "Stable", "Rising"],
  risk: ["Risk-off", "Neutral", "Risk-on"],
  usd: ["Weak", "Neutral", "Strong"],
  volatility: ["High", "Normal", "Low"],
};
const COLORS = ["var(--neg)", "var(--mid)", "var(--pos)"];

/** Weekly sampled regime history: one row per dimension, diverging colour + state name in each cell's tooltip. */
export default function RegimeStrip({ rows, compact = false }: { rows: RegimeRow[]; compact?: boolean }) {
  if (!rows.length) return <div className="empty">No regime history yet.</div>;
  const weekly = rows.filter((_, i) => i % 5 === 0 || i === rows.length - 1);
  const W = 1000, rowH = compact ? 14 : 18, labelW = 90, gap = compact ? 4 : 6;
  const cw = (W - labelW) / weekly.length;
  const dims = Object.keys(STATES);
  const years = weekly.map((r, i) => ({ y: compact ? r.date.slice(0, 7) : r.date.slice(0, 4), i }))
    .filter((v, k, a) => k === 0 || v.y !== a[k - 1].y)
    .filter((v, k) => !compact || k % 3 === 0)
    .filter((v, k, a) => k === 0 ? a.length < 2 || (a[1].i - v.i) * cw > 40 : true);
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${dims.length * (rowH + gap) + 20}`} role="img" aria-label="Regime history by dimension">
        {dims.map((d, r) => (
          <g key={d} transform={`translate(0 ${r * (rowH + gap)})`}>
            <text x={0} y={rowH - 5} fill="var(--muted)" fontSize="11" fontFamily="var(--mono)">{d}</text>
            {weekly.map((row, i) => {
              const v = (row as any)[d] as string | null;
              const k = v ? STATES[d].indexOf(v) : -1;
              return (
                <rect key={i} x={labelW + i * cw} y={0} width={Math.max(cw - 0.5, 0.5)} height={rowH}
                  fill={k >= 0 ? COLORS[k] : "var(--surface-2)"} opacity={k === 1 ? 0.9 : 0.85}>
                  <title>{`${row.date} · ${d}: ${v ?? "n/a"}`}</title>
                </rect>
              );
            })}
          </g>
        ))}
        {years.map(({ y, i }) => (
          <text key={y} x={labelW + i * cw} y={dims.length * (rowH + gap) + 12} fill="var(--muted)" fontSize="10.5" fontFamily="var(--mono)">{y}</text>
        ))}
      </svg>
      {!compact && <div className="legend" style={{ marginTop: 6 }}>
        <span><i style={{ background: "var(--pos)", height: 8, width: 8 }} />Strong growth · Rising inflation · Risk-on · Strong USD · Low vol</span>
        <span><i style={{ background: "var(--mid)", height: 8, width: 8 }} />Neutral</span>
        <span><i style={{ background: "var(--neg)", height: 8, width: 8 }} />Weak · Falling · Risk-off · Weak USD · High vol</span>
      </div>}
    </div>
  );
}
