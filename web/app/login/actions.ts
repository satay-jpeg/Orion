"use server";
import { redirect } from "next/navigation";
import { sessionClient } from "@/lib/supabase/server";

export async function signIn(_: { error?: string } | undefined, form: FormData) {
  const email = String(form.get("email") ?? "").trim().slice(0, 200);
  const password = String(form.get("password") ?? "").slice(0, 200);
  if (!email || !password) return { error: "Email and password are required." };
  const sb = await sessionClient();
  const { error } = await sb.auth.signInWithPassword({ email, password });
  // Deliberately generic message: do not reveal whether the account exists.
  if (error) return { error: "Sign-in failed." };
  redirect("/admin");
}

export async function signOut() {
  const sb = await sessionClient();
  await sb.auth.signOut();
  redirect("/");
}
