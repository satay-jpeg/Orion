import { publicClient } from "./supabase/public";

export type Component = { value: number | null; weight: number; contribution: number; description: string };
export type SignalRow = { date: string; symbol: string; composite: number; label: string; components: Record<string, Component>; completeness: number };
export type RegimeRow = { date: string; growth: string | null; inflation: string | null; risk: string | null; usd: string | null; volatility: string | null; label: string; inputs: Record<string, number | null> };
export type Snapshot = { date: string; what_changed: any; analogues: any; theses: Record<string, any>; scenarios: any };

async function safe<T>(p: PromiseLike<{ data: T | null; error: any }>, fallback: T): Promise<T> {
  try {
    const { data, error } = await p;
    if (error) { console.error(error.message); return fallback; }
    return (data ?? fallback) as T;
  } catch (e) { console.error(e); return fallback; }
}

export async function latestSnapshot(): Promise<Snapshot | null> {
  const sb = publicClient();
  const rows = await safe(sb.from("market_snapshots").select("*").order("date", { ascending: false }).limit(1), [] as Snapshot[]);
  return rows[0] ?? null;
}

export async function latestSignals(): Promise<SignalRow[]> {
  const sb = publicClient();
  const last = await safe(sb.from("signals").select("date").order("date", { ascending: false }).limit(1), [] as { date: string }[]);
  if (!last[0]) return [];
  return safe(sb.from("signals").select("*").eq("date", last[0].date), [] as SignalRow[]);
}

export async function signalHistory(symbol: string, days = 1500): Promise<SignalRow[]> {
  const sb = publicClient();
  const since = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
  return safe(sb.from("signals").select("date,composite,components,completeness,label,symbol").eq("symbol", symbol)
    .gte("date", since).order("date").limit(5000), [] as SignalRow[]);
}

export async function marketIndex(symbol: string, days = 1500) {
  const sb = publicClient();
  const since = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
  return safe(sb.from("market_index_public").select("date,index_value").eq("symbol", symbol).gte("date", since)
    .order("date").limit(5000), [] as { date: string; index_value: number }[]);
}

export async function regimeHistory(days = 3650): Promise<RegimeRow[]> {
  const sb = publicClient();
  const since = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
  const out: RegimeRow[] = [];
  // paginate past the default 1000-row limit
  for (let from = 0; from < 20000; from += 1000) {
    const rows = await safe(sb.from("regimes").select("*").gte("date", since).order("date").range(from, from + 999), [] as RegimeRow[]);
    out.push(...rows);
    if (rows.length < 1000) break;
  }
  return out;
}

export async function latestBacktest() {
  const sb = publicClient();
  const runs = await safe(sb.from("backtest_runs").select("*").eq("is_latest", true).order("created_at", { ascending: false }).limit(1), [] as any[]);
  const run = runs[0];
  if (!run) return null;
  const series: { date: string; segment: string; equity: number; drawdown: number }[] = [];
  for (let from = 0; from < 30000; from += 1000) {
    const rows = await safe(sb.from("backtest_series").select("date,segment,equity,drawdown").eq("run_id", run.id)
      .order("date").range(from, from + 999), [] as typeof series);
    series.push(...rows);
    if (rows.length < 1000) break;
  }
  const trades = await safe(sb.from("backtest_trades").select("symbol,segment,direction,entry_date,exit_date,return_pct,bars,exit_reason")
    .eq("run_id", run.id).order("entry_date", { ascending: false }).limit(40), [] as any[]);
  return { run, series, trades };
}

export async function publicPerformance() {
  const sb = publicClient();
  return safe(sb.from("performance_public").select("date,nav_index,drawdown").order("date").limit(5000),
    [] as { date: string; nav_index: number; drawdown: number }[]);
}

export async function lastRun() {
  const sb = publicClient();
  const rows = await safe(sb.from("pipeline_runs").select("started_at,finished_at,status,kind,freshness")
    .eq("kind", "daily").order("started_at", { ascending: false }).limit(1), [] as any[]);
  return rows[0] ?? null;
}

export async function dataSources() {
  const sb = publicClient();
  return safe(sb.from("data_sources").select("*").order("provider"), [] as any[]);
}

export async function macroHistory(ids: string[], days = 1100) {
  const sb = publicClient();
  const since = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
  const out: { series_id: string; date: string; value: number }[] = [];
  for (let from = 0; from < 20000; from += 1000) {
    const rows = await safe(sb.from("macro_series").select("series_id,date,value").in("series_id", ids).gte("date", since)
      .order("date").range(from, from + 999), [] as typeof out);
    out.push(...rows);
    if (rows.length < 1000) break;
  }
  return out;
}
