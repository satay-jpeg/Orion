import { isNum } from "@/lib/format";

/** Diverging bar centred on zero. Blue = supportive, red = negative; the number is always printed alongside. */
export default function ScoreBar({ value, max = 3, width = 120 }: { value: number | null | undefined; max?: number; width?: number }) {
  const v = isNum(value) ? Math.max(-max, Math.min(max, value)) : 0;
  const half = 50 * (Math.abs(v) / max);
  const style = v >= 0
    ? { left: "50%", width: `${half}%`, background: "var(--pos)" }
    : { left: `${50 - half}%`, width: `${half}%`, background: "var(--neg)" };
  return (
    <div className="dbar" style={{ width }} aria-hidden>
      {isNum(value) && <span className={v < 0 ? "neg" : ""} style={style} />}
    </div>
  );
}
