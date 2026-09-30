import LineChart from "@/components/LineChart";
import ScoreBar from "@/components/ScoreBar";
import { requireAdmin } from "@/lib/supabase/server";
import { NAMES, isNum, num, pct, signed, tone } from "@/lib/format";
import { signOut } from "../login/actions";
import ConfigForm from "./ConfigForm";
import SizeCalculator from "./SizeCalculator";

export const dynamic = "force-dynamic";
export const metadata = { robots: { index: false, follow: false } };

const usd = (v: unknown, dp = 0) => (isNum(v) ? (v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: dp, minimumFractionDigits: dp }) : "—");

export default async function Admin() {
  const { sb, user, isAdmin } = await requireAdmin();
  if (!user || !isAdmin) {
    return (
      <div style={{ maxWidth: 420, margin: "64px auto" }} className="board"><div className="panel">
        <h2>Not authorised</h2>
        <p className="small ink2">This account is not an ORION admin. The public research pages are available from the menu.</p>
        <form action={signOut}><button type="submit">Sign out</button></form>
      </div></div>
    );
  }

  const [eq, cfgQ, jr, od] = await Promise.all([
    sb.from("equity_snapshots").select("*").order("date").limit(5000),
    sb.from("agent_config").select("*").eq("id", 1).single(),
    sb.from("journal").select("*").order("id", { ascending: false }).limit(60),
    sb.from("orders").select("id,created_at,date,symbol,units,intent,status,fill_price,stop_price,error").order("id", { ascending: false }).limit(40),
  ]);
  const equity = eq.data ?? [];
  const last = equity.at(-1);
  const prev = equity.at(-2);
  const posQ = last ? await sb.from("positions_snapshot").select("*").eq("date", last.date) : { data: [] as any[] };
  const positions = (posQ.data ?? []).filter((p: any) => p.units !== 0);
  const cfg = cfgQ.data ?? {};
  const risk = last?.risk ?? {};
  const corr: Record<string, Record<string, number>> = risk.correlation ?? {};
  const corrSyms = Object.keys(corr);
  const exposure: Record<string, number> = last?.currency_exposure ?? {};

  return (
    <>
      <div className="pagehead">
        <div>
          <h1>Book</h1>
          <p>Private view of the OANDA practice account the agent manages. Signed in as <span className="mono">{user.email}</span>.</p>
        </div>
        <form action={signOut}><button type="submit">Sign out</button></form>
      </div>

      <section className="board cols-12">
        <div className="panel span-12">
          <div className="figs" style={{ border: "1px solid var(--line)" }}>
            <div className="fig"><div className="caps">NAV</div><div className="v">{usd(last?.nav)}</div><div className="s">{last?.date ?? "no snapshot yet"}</div></div>
            <div className="fig"><div className="caps">Day P&amp;L</div><div className={`v ${tone((last?.nav ?? 0) - (prev?.nav ?? last?.nav ?? 0))}`}>{prev ? usd(last.nav - prev.nav) : "—"}</div><div className="s">{prev ? pct(last.nav / prev.nav - 1, 2) : ""}</div></div>
            <div className="fig"><div className="caps">Unrealised</div><div className={`v ${tone(last?.unrealized_pl)}`}>{usd(last?.unrealized_pl)}</div></div>
            <div className="fig"><div className="caps">Drawdown</div><div className="v">{pct(last?.drawdown, 1, false)}</div><div className="s">halt at −{pct(cfg.halt_drawdown, 0, false)}</div></div>
            <div className="fig"><div className="caps">Gross leverage</div><div className="v">{num(last?.gross_exposure, 2)}×</div><div className="s">limit {num(cfg.max_gross_leverage, 1)}×</div></div>
            <div className="fig"><div className="caps">Portfolio vol</div><div className="v">{pct(last?.portfolio_vol, 1, false)}</div><div className="s">60d, correlation-adjusted</div></div>
            <div className="fig"><div className="caps">Agent</div><div className="v" style={{ fontSize: 16, color: cfg.trading_enabled ? "var(--up)" : "var(--warn)" }}>{cfg.trading_enabled ? "● Trading" : "○ Dry run"}</div><div className="s">{cfg.halted_reason ?? "daily after NY close"}</div></div>
          </div>
        </div>

        <div className="panel span-8">
          <h2>NAV</h2>
          <LineChart height={220} format="usd" series={[{ name: "NAV (USD)", color: "var(--accent)", data: equity.map((e: any) => ({ x: e.date, y: e.nav })) }]} />
        </div>
        <div className="panel span-4">
          <h2>Currency &amp; commodity exposure (× NAV)</h2>
          {Object.keys(exposure).length ? (
            <table className="data"><tbody>
              {Object.entries(exposure).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([k, v]) => (
                <tr key={k}><td className="mono">{k}</td><td className="n">{signed(v, 2)}</td><td><ScoreBar value={v} max={Math.max(1.5, cfg.max_currency_exposure ?? 1.5)} width={110} /></td></tr>
              ))}
            </tbody></table>
          ) : <div className="empty">Flat.</div>}
          <p className="tiny muted" style={{ marginTop: 8 }}>Positions decomposed into their currency legs, so a long USD/JPY and a long gold both show up in the USD line.</p>
        </div>

        <div className="panel span-7">
          <h2>Positions</h2>
          {positions.length ? (
            <div className="tablewrap"><table className="data">
              <thead><tr><th>Market</th><th className="n">Units</th><th className="n">Avg price</th><th className="n">Notional</th><th className="n">Weight</th><th className="n">Unreal. P&amp;L</th><th className="n">Risk contrib.</th></tr></thead>
              <tbody>
                {positions.map((p: any) => (
                  <tr key={p.symbol}>
                    <td>{NAMES[p.symbol] ?? p.symbol}</td>
                    <td className={`n ${tone(p.units)}`}>{p.units.toLocaleString()}</td>
                    <td className="n">{num(p.avg_price, 4)}</td>
                    <td className="n">{usd(p.notional_usd)}</td>
                    <td className="n">{signed(p.weight, 2)}×</td>
                    <td className={`n ${tone(p.unrealized_pl)}`}>{usd(p.unrealized_pl)}</td>
                    <td className="n">{pct(risk.risk_contribution?.[p.symbol], 0, false)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : <div className="empty">No open positions.</div>}
        </div>
        <div className="panel span-5">
          <h2>Correlation of held markets (60d)</h2>
          {corrSyms.length > 1 ? (
            <div className="tablewrap"><table className="data">
              <thead><tr><th />{corrSyms.map((s) => <th key={s} className="n">{(NAMES[s] ?? s).replace("/", "")}</th>)}</tr></thead>
              <tbody>
                {corrSyms.map((a) => (
                  <tr key={a}><td>{NAMES[a] ?? a}</td>{corrSyms.map((b) => {
                    const v = corr[a]?.[b];
                    const bg = a === b || !isNum(v) ? undefined : `rgba(${v >= 0 ? "57,135,229" : "230,103,103"},${(Math.abs(v) * 0.7).toFixed(2)})`;
                    return <td key={b} className="n" style={{ background: bg }}>{a === b ? "·" : num(v, 2)}</td>;
                  })}</tr>
                ))}
              </tbody>
            </table></div>
          ) : <div className="empty">Needs two or more positions.</div>}
          {isNum(risk.diversification_ratio) && <p className="small ink2">Diversification ratio {num(risk.diversification_ratio, 2)} (sum of stand-alone vols ÷ portfolio vol).</p>}
        </div>

        <div className="panel span-7">
          <h2>Agent journal</h2>
          <ul className="plain">
            {(jr.data ?? []).map((j: any) => (
              <li key={j.id}>
                <div className="small"><span className="mono muted">{j.date}</span> <span className={`chip ${j.action.startsWith("enter") ? "pos" : j.action === "exit" || j.action === "halt" ? "neg" : ""}`}>{j.action}</span></div>
                <div style={{ marginTop: 4 }}>{j.summary}</div>
              </li>
            ))}
            {!(jr.data ?? []).length && <li className="muted">No journal entries yet.</li>}
          </ul>
        </div>
        <div className="panel span-5">
          <h2>Orders</h2>
          <div className="tablewrap"><table className="data">
            <thead><tr><th>Date</th><th>Market</th><th className="n">Units</th><th>Intent</th><th>Status</th></tr></thead>
            <tbody>
              {(od.data ?? []).map((o: any) => (
                <tr key={o.id} title={o.error ?? ""}>
                  <td className="mono small">{o.date}</td><td>{NAMES[o.symbol] ?? o.symbol}</td>
                  <td className={`n ${tone(o.units)}`}>{Number(o.units).toLocaleString()}</td><td className="small">{o.intent}</td>
                  <td className={`small ${o.status === "filled" ? "up" : o.status === "dry_run" ? "muted" : "down"}`}>{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>

        <div className="panel span-7">
          <h2>Agent settings</h2>
          <ConfigForm cfg={cfg} />
        </div>
        <div className="panel span-5">
          <h2>Position size calculator</h2>
          <SizeCalculator />
        </div>
      </section>
    </>
  );
}
