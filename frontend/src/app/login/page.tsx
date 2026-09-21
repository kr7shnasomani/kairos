"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { getMe, login } from "@/lib/auth";

function workspacePath(role?: string) {
  return role === "field_worker" ? "/briefs" : "/management";
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Deliberately no "already signed in → skip to workspace" auto-redirect here — every
  // visit to /login shows the sign-in form, even with a valid stored token. Otherwise a
  // leftover session from earlier testing silently swaps the page mid-view, which is
  // exactly the wrong thing to have happen while presenting.

  // Real login → POST /auth/login (Supabase). Stores tokens, then routes directly in.
  async function doLogin(em: string, pw: string) {
    setError(null);
    setBusy(true);
    try {
      await login(em, pw);
      const user = await getMe();
      router.push(workspacePath(user?.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setBusy(false);
    }
  }

  function signIn(e: React.FormEvent) {
    e.preventDefault();
    void doLogin(email, password);
  }

  // One-click demo → signs straight into the seeded admin account.
  function tryDemo() {
    void doLogin("admin@kairos.local", "KairosAdmin123!");
  }

  return (
    <main className="relative grid min-h-dvh place-items-center bg-page px-5 py-20">
      <title>Kairos: Sign in</title>
      <Link href="/" aria-label="Back to landing page" className="absolute left-5 top-5 grid size-10 place-items-center rounded-lg border border-line bg-surface text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m14 6-6 6 6 6" />
        </svg>
      </Link>
      <div className="absolute right-5 top-5">
        <ThemeToggle />
      </div>

      <div data-testid="login-workspace" className="grid w-full max-w-6xl overflow-hidden rounded-3xl border border-line bg-surface shadow-xl lg:min-h-[680px] lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.72fr)]">
        <section data-testid="login-context" className="relative hidden overflow-hidden bg-ink p-10 text-canvas lg:flex lg:flex-col lg:justify-between">
          <div aria-hidden="true" className="absolute -right-24 -top-24 size-80 rounded-full bg-accent opacity-20 blur-3xl" />
          <div className="relative">
            <p className="text-label font-bold uppercase tracking-[0.12em] text-accent">Evidence-linked operations</p>
            <h2 className="mt-4 max-w-lg text-4xl font-semibold leading-tight text-balance">Enter the workspace with the context your role needs.</h2>
            <p className="mt-4 max-w-lg text-body leading-relaxed text-canvas/70">Supervisors see plant decisions and live service state. Engineers move through evidence and governance. Field teams get focused, touch-first workflows.</p>
          </div>

          <div className="relative rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur">
            <div className="flex items-center justify-between border-b border-white/10 pb-3 text-label"><span className="font-semibold text-canvas">Kairos workspace</span><span className="text-canvas/55">Role-aware</span></div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-white/5 p-3"><p className="text-micro uppercase tracking-wide text-canvas/50">Decisions</p><div className="mt-3 space-y-2"><span className="block h-2 rounded-full bg-white/15" /><span className="block h-2 w-2/3 rounded-full bg-white/10" /></div></div>
              <div className="rounded-xl bg-white/5 p-3"><p className="text-micro uppercase tracking-wide text-canvas/50">Evidence</p><div className="mt-3 space-y-2"><span className="block h-2 rounded-full bg-white/15" /><span className="block h-2 w-4/5 rounded-full bg-white/10" /></div></div>
            </div>
            <p className="mt-4 text-caption text-canvas/60">Authenticated access routes directly to your operational overview.</p>
          </div>
        </section>

        <section data-testid="login-form-panel" className="flex items-center justify-center px-5 py-10 sm:px-10">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center text-center">
          <Image src="/logo.png" alt="Kairos" width={48} height={48} priority className="size-12 rounded-xl object-cover" />
          <h1 className="mt-4 text-display font-semibold">Sign in to Kairos</h1>
          <p className="mt-1.5 text-body text-muted">The right knowledge, at the moment of action.</p>
        </div>

        <form onSubmit={signIn} className="mt-7 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-caption font-medium text-muted">Email</span>
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="engineer@kairos.local"
              className="min-h-11 rounded-lg border border-line bg-page px-3.5 text-sm outline-none focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-caption font-medium text-muted">Password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="min-h-11 rounded-lg border border-line bg-page px-3.5 text-sm outline-none focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent"
            />
          </label>
          {error && (
            <p className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] px-3 py-2 text-caption text-danger">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy}
            className="mt-1 min-h-11 rounded-lg bg-ink text-sm font-semibold text-canvas transition-opacity hover:opacity-90 disabled:opacity-60">
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <button type="button" onClick={tryDemo} disabled={busy}
            className="min-h-11 rounded-lg border border-line bg-surface text-sm font-semibold text-ink transition-colors hover:bg-surface-2 disabled:opacity-60">
            Explore the live demo
          </button>
        </form>
      </div>
        </section>
      </div>
    </main>
  );
}
