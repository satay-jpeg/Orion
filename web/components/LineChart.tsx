"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type Series = { name: string; color: string; data: { x: string; y: number }[]; dashed?: boolean };
type Fmt = "pct" | "num" | "index" | "pp" | "score" | "usd";

const fmt = (f: Fmt, v: number) => {
  if (!Number.isFinite(v)) return "—";
  switch (f) {
    case "pct": return (v * 100).toFixed(1) + "%";
    case "pp": return v.toFixed(2) + "%";
    case "index": return v.toFixed(1);
    case "score": return (v > 0 ? "+" : "") + v.toFixed(2);
    case "usd": return Math.abs(v) >= 1e4 ? "$" + (v / 1000).toFixed(1) + "k" : "$" + v.toFixed(0);
    default: return v.toFixed(2);
  }
};

function niceTicks(min: number, max: number, n = 4) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const step0 = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n + 1) ?? step0;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-12; t += step) ticks.push(+t.toFixed(10));
  return ticks;
}

export default function LineChart({
  series, height = 220, format = "num", zero = false, bands = [], yDomain, title,
}: {
  series: Series[]; height?: number; format?: Fmt; zero?: boolean;
  bands?: { from: string; to: string; label: string }[]; yDomain?: [number, number]; title?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(720);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const xs = useMemo(() => Array.from(new Set(series.flatMap((s) => s.data.map((d) => d.x)))).sort(), [series]);
  const maps = useMemo(() => series.map((s) => new Map(s.data.map((d) => [d.x, d.y]))), [series]);

  if (!xs.length) return <div className="empty">No data yet. The pipeline fills this after its first run.</div>;

  const pad = { l: 48, r: 12, t: 10, b: 22 };
  const iw = w - pad.l - pad.r;
  const ih = height - pad.t - pad.b;
  const all = series.flatMap((s) => s.data.map((d) => d.y)).filter(Number.isFinite);
  let [lo, hi] = yDomain ?? [Math.min(...all), Math.max(...all)];
  if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const padY = (hi - lo) * 0.06 || 1;
  if (!yDomain) { lo -= padY; hi += padY; }
  const ticks = niceTicks(lo, hi);
  const X = (i: number) => pad.l + (xs.length === 1 ? iw / 2 : (i / (xs.length - 1)) * iw);
  const Y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * ih;
  const idx = new Map(xs.map((x, i) => [x, i]));

  const paths = series.map((s, k) => {
    let d = "";
    let pen = false;
    xs.forEach((x, i) => {
      const v = maps[k].get(x);
      if (v === undefined || !Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  });

  // x ticks at calendar boundaries (years for long spans, months otherwise), thinned to fit
  const long = xs.length > 400;
  const key = (x: string) => (long ? x.slice(0, 4) : x.slice(0, 7));
  const bounds: number[] = [];
  xs.forEach((x, i) => { if (i > 0 && key(x) !== key(xs[i - 1])) bounds.push(i); });
  const minGap = 64;
  const xticks: number[] = [];
  for (const i of bounds) if (!xticks.length || X(i) - X(xticks[xticks.length - 1]) >= minGap) xticks.push(i);
  if (!xticks.length) xticks.push(0);
  const xlabel = (x: string) => {
    const d = new Date(x + "T00:00:00Z");
    if (long) return String(d.getUTCFullYear());
    const m = d.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
    return d.getUTCMonth() === 0 || xs.length < 70 ? `${m} ’${String(d.getUTCFullYear()).slice(2)}` : m;
  };

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = e.clientX - r.left;
    const i = Math.round(((px - pad.l) / iw) * (xs.length - 1));
    setHover(Math.max(0, Math.min(xs.length - 1, i)));
  };

  return (
    <div className="chart" ref={ref}>
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => (
            <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>
          ))}
        </div>
      )}
      <svg width={w} height={height} role="img" aria-label={title ?? series.map((s) => s.name).join(", ")}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {bands.map((b) => {
          const a = idx.get(b.from) ?? xs.findIndex((x) => x >= b.from);
          const z = idx.get(b.to) ?? xs.length - 1;
          if (a < 0) return null;
          return (
            <g key={b.label}>
              <rect x={X(a)} y={pad.t} width={Math.max(1, X(z) - X(a))} height={ih} fill="var(--surface-2)" />
              <text x={X(a) + 6} y={pad.t + 12} fill="var(--muted)" fontSize="10.5" fontFamily="var(--mono)">{b.label}</text>
            </g>
          );
        })}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={w - pad.r} y1={Y(t)} y2={Y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text x={pad.l - 8} y={Y(t) + 3.5} textAnchor="end" fill="var(--muted)" fontSize="10.5" fontFamily="var(--mono)">{fmt(format, t)}</text>
          </g>
        ))}
        {zero && lo < 0 && hi > 0 && <line x1={pad.l} x2={w - pad.r} y1={Y(0)} y2={Y(0)} stroke="var(--line-strong)" strokeWidth={1} />}
        {xticks.map((i) => (
          <text key={i} x={X(i)} y={height - 6} textAnchor={X(i) > w - pad.r - 30 ? "end" : "middle"}
            fill="var(--muted)" fontSize="10.5" fontFamily="var(--mono)">{xlabel(xs[i])}</text>
        ))}
        {paths.map((d, k) => (
          <path key={series[k].name} d={d} fill="none" stroke={series[k].color} strokeWidth={series.length > 3 ? 1.5 : 2}
            strokeDasharray={series[k].dashed ? "4 3" : undefined} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {hover !== null && (
          <g>
            <line x1={X(hover)} x2={X(hover)} y1={pad.t} y2={pad.t + ih} stroke="var(--muted)" strokeWidth={1} />
            {series.map((s, k) => {
              const v = maps[k].get(xs[hover]);
              return v === undefined ? null : (
                <circle key={s.name} cx={X(hover)} cy={Y(v)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
              );
            })}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: Math.min(X(hover) + 12, w - 170), top: 18 }}>
          <div className="muted">{xs[hover]}</div>
          {series.map((s, k) => {
            const v = maps[k].get(xs[hover]);
            return v === undefined ? null : (
              <div key={s.name}><span style={{ color: s.color }}>■</span> {s.name} <b>{fmt(format, v)}</b></div>
            );
          })}
        </div>
      )}
    </div>
  );
}
