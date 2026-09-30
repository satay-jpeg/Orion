"use client";
import { useActionState } from "react";
import { saveConfig } from "./actions";

const FIELDS: [string, string, number][] = [
  ["risk_per_trade", "Risk per trade (fraction of NAV)", 0.001],
  ["stop_atr_multiple", "Stop distance (× ATR20)", 0.1],
  ["entry_threshold", "Entry threshold (|composite|)", 0.05],
  ["exit_threshold", "Exit threshold", 0.05],
  ["max_position_weight", "Max position (× NAV notional)", 0.1],
  ["max_gross_leverage", "Max gross leverage (× NAV)", 0.1],
  ["max_currency_exposure", "Max single-currency exposure (× NAV)", 0.1],
  ["halt_drawdown", "Circuit breaker drawdown", 0.01],
  ["rebalance_band", "Resize only if size off by more than", 0.05],
];

export default function ConfigForm({ cfg }: { cfg: Record<string, any> }) {
  const [state, action, pending] = useActionState(saveConfig, undefined);
  return (
    <form action={action}>
      <label className="switch" style={{ marginBottom: 14 }}>
        <input type="checkbox" name="trading_enabled" defaultChecked={!!cfg.trading_enabled} />
        <span><b>Trading enabled</b> <span className="muted small">(off = agent logs intended orders as dry runs)</span></span>
      </label>
      {cfg.halted_reason && <div className="notice" style={{ marginBottom: 12 }}>Halted: {cfg.halted_reason}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: "0 16px" }}>
        {FIELDS.map(([k, label, step]) => (
          <div className="field" key={k}>
            <label htmlFor={k}>{label}</label>
            <input id={k} name={k} type="number" step={step} defaultValue={cfg[k]} />
          </div>
        ))}
      </div>
      <button className="primary" disabled={pending} type="submit">{pending ? "Saving…" : "Save settings"}</button>
      {state?.msg && <span className="small" style={{ marginLeft: 12 }}>{state.msg}</span>}
    </form>
  );
}
