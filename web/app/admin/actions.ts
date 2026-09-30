"use server";
import { revalidatePath } from "next/cache";
import { requireAdmin } from "@/lib/supabase/server";

const BOUNDS: Record<string, [number, number]> = {
  risk_per_trade: [0, 0.02], stop_atr_multiple: [0.5, 10], entry_threshold: [0, 3], exit_threshold: [-1, 3],
  max_gross_leverage: [0, 10], max_position_weight: [0, 5], max_currency_exposure: [0, 10], halt_drawdown: [0.01, 0.5],
  rebalance_band: [0, 1],
};

export async function saveConfig(_: { msg?: string } | undefined, form: FormData) {
  const { sb, user, isAdmin } = await requireAdmin();
  if (!user || !isAdmin) return { msg: "Not authorised." };
  const update: Record<string, unknown> = { updated_at: new Date().toISOString(), updated_by: user.id };
  for (const [k, [lo, hi]] of Object.entries(BOUNDS)) {
    const raw = form.get(k);
    if (raw === null || raw === "") continue;
    const v = Number(raw);
    if (!Number.isFinite(v) || v < lo || v > hi) return { msg: `${k} must be between ${lo} and ${hi}.` };
    update[k] = v;
  }
  const enabled = form.get("trading_enabled") === "on";
  update.trading_enabled = enabled;
  if (enabled) update.halted_reason = null;
  // RLS + column grants in the database are the real guard; this check just gives a clear message.
  const { error } = await sb.from("agent_config").update(update).eq("id", 1);
  if (error) return { msg: "Save failed: " + error.message };
  revalidatePath("/admin");
  return { msg: "Saved. Takes effect on the next agent run." };
}
