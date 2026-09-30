export const INSTRUMENT_ORDER = ["USD_JPY", "EUR_USD", "AUD_USD", "USD_CAD", "XAU_USD", "BCO_USD", "XCU_USD"] as const;
export const NAMES: Record<string, string> = {
  USD_JPY: "USD/JPY", EUR_USD: "EUR/USD", AUD_USD: "AUD/USD", USD_CAD: "USD/CAD",
  XAU_USD: "Gold", BCO_USD: "Brent", XCU_USD: "Copper",
};

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function pct(v: unknown, dp = 1, sign = true) {
  if (!isNum(v)) return "—";
  const s = (v * 100).toFixed(dp);
  return (sign && v > 0 ? "+" : "") + s + "%";
}
/** value already in percent units */
export function pp(v: unknown, dp = 1, sign = true) {
  if (!isNum(v)) return "—";
  return (sign && v > 0 ? "+" : "") + v.toFixed(dp) + "%";
}
export function num(v: unknown, dp = 2, sign = false) {
  if (!isNum(v)) return "—";
  return (sign && v > 0 ? "+" : "") + v.toFixed(dp);
}
export function signed(v: unknown, dp = 2) { return num(v, dp, true); }
export const tone = (v: unknown) => (!isNum(v) || v === 0 ? "" : v > 0 ? "up" : "down");
export const arrow = (v: unknown) => (!isNum(v) || Math.abs(v) < 1e-9 ? "·" : v > 0 ? "▲" : "▼");

export function daysOld(date?: string | null) {
  if (!date) return Infinity;
  return Math.floor((Date.now() - new Date(date + "T00:00:00Z").getTime()) / 86_400_000);
}
