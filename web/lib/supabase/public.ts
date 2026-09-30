import { createClient } from "@supabase/supabase-js";

/** Session-less anon client for public research pages (cacheable, RLS: public tables only). */
export function publicClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Supabase env vars are not set");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}
