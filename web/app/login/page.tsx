"use client";
import { useActionState } from "react";
import { signIn } from "./actions";

export default function Login() {
  const [state, action, pending] = useActionState(signIn, undefined);
  return (
    <div style={{ maxWidth: 360, margin: "64px auto" }}>
      <div className="board"><div className="panel">
        <h2>Admin sign-in</h2>
        <p className="small muted" style={{ marginTop: 0 }}>The research pages are public. The portfolio book is for the owner only; there is no public sign-up.</p>
        {process.env.NEXT_PUBLIC_DEMO_MODE === "1" && <p className="notice small">Demo mode: any email and password will sign you in.</p>}
        <form action={action}>
          <div className="field"><label htmlFor="email">Email</label><input id="email" name="email" type="email" autoComplete="username" required /></div>
          <div className="field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete="current-password" required /></div>
          {state?.error && <p className="small down">{state.error}</p>}
          <button className="primary" disabled={pending} type="submit">{pending ? "Signing in…" : "Sign in"}</button>
        </form>
      </div></div>
    </div>
  );
}
