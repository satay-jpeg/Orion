import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/** Cookie-bound client: queries run as the signed-in user, so RLS applies to them. */
export async function sessionClient() {
  const store = await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (list) => {
        try {
          list.forEach(({ name, value, options }) => store.set(name, value, options));
        } catch {
          // called from a Server Component: middleware refreshes the session instead
        }
      },
    },
  });
}

/** Returns the user only if they are listed in public.admins (checked in the database). */
export async function requireAdmin() {
  const sb = await sessionClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return { sb, user: null, isAdmin: false } as const;
  const { data, error } = await sb.rpc("is_admin");
  return { sb, user, isAdmin: !error && data === true } as const;
}
