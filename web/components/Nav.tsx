"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Overview"], ["/signals", "Signals"], ["/regime", "Regime"], ["/backtest", "Backtest"],
  ["/performance", "Performance"], ["/methodology", "Methodology"],
] as const;

export default function Nav() {
  const path = usePathname();
  const active = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));
  return (
    <nav className="nav" aria-label="Primary">
      {LINKS.map(([h, l]) => (
        <Link key={h} href={h} aria-current={active(h) ? "page" : undefined}>{l}</Link>
      ))}
      <Link href="/admin" aria-current={active("/admin") ? "page" : undefined} style={{ marginLeft: "auto" }}>Admin</Link>
    </nav>
  );
}
