"use client";
import { useState } from "react";

const PIP: Record<string, number> = { USD_JPY: 0.01, EUR_USD: 0.0001, AUD_USD: 0.0001, USD_CAD: 0.0001 };

/** Position sizing: units such that the stop loses exactly `risk` of the account (quote converted to USD). */
export default function SizeCalculator() {
  const [acct, setAcct] = useState(100000);
  const [risk, setRisk] = useState(0.5);
  const [sym, setSym] = useState("USD_JPY");
  const [price, setPrice] = useState(150);
  const [stopPips, setStopPips] = useState(80);
  const pip = PIP[sym] ?? 1;
  const dist = stopPips * pip;
  const q2usd = sym.startsWith("USD_") ? 1 / price : 1;
  const riskUsd = acct * risk / 100;
  const units = dist > 0 ? riskUsd / (dist * q2usd) : 0;
  const notional = sym.startsWith("USD_") ? units : units * price;
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: "0 12px" }}>
        <div className="field"><label>Account (USD)</label><input type="number" value={acct} onChange={(e) => setAcct(+e.target.value)} /></div>
        <div className="field"><label>Risk per trade (%)</label><input type="number" step={0.05} value={risk} onChange={(e) => setRisk(+e.target.value)} /></div>
        <div className="field"><label>Market</label>
          <select value={sym} onChange={(e) => setSym(e.target.value)} style={{ background: "var(--page)", color: "var(--ink)", border: "1px solid var(--line-strong)", padding: 8, borderRadius: 2 }}>
            {["USD_JPY", "EUR_USD", "AUD_USD", "USD_CAD", "XAU_USD", "BCO_USD", "XCU_USD"].map((s) => <option key={s}>{s}</option>)}
          </select></div>
        <div className="field"><label>Entry price</label><input type="number" step="any" value={price} onChange={(e) => setPrice(+e.target.value)} /></div>
        <div className="field"><label>{PIP[sym] ? "Stop (pips)" : "Stop (price units)"}</label><input type="number" step="any" value={stopPips} onChange={(e) => setStopPips(+e.target.value)} /></div>
      </div>
      <table className="data"><tbody>
        <tr><td>Maximum loss at stop</td><td className="n">${riskUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td></tr>
        <tr><td>Position size</td><td className="n">{units.toLocaleString(undefined, { maximumFractionDigits: 0 })} units</td></tr>
        <tr><td>Notional (USD)</td><td className="n">${notional.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td></tr>
        <tr><td>Leverage</td><td className="n">{(notional / acct).toFixed(2)}×</td></tr>
      </tbody></table>
    </div>
  );
}
