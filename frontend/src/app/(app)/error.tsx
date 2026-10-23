"use client";

import { useEffect, useSyncExternalStore } from "react";
import { Button } from "@/components/ui";
import { accessTokenExpired, expireSession, refreshAccessToken, refreshedThisPageLoad } from "@/lib/api";

const noSubscribe = () => () => {};
const RELOAD_GUARD = "kairos-error-reload";

function reloadedJustNow(): boolean {
  try {
    const at = Number(sessionStorage.getItem(RELOAD_GUARD) || 0);
    return Date.now() - at < 20_000;
  } catch {
    return false;
  }
}

/** A server page failed and a session refresh can fix it: the token has expired, or it was refreshed
 *  during this page load (the shell refreshes before it renders the page, so by the time this
 *  boundary renders the token already looks valid, but the server rendered with the old cookie).
 *  Never twice within 20 s, so a page that fails for another reason shows its error instead of looping. */
function sessionRecoverable(): boolean {
  return !reloadedJustNow() && (accessTokenExpired() || refreshedThisPageLoad());
}

function reloadOnce(): void {
  try { sessionStorage.setItem(RELOAD_GUARD, String(Date.now())); } catch { /* storage disabled */ }
  window.location.reload();
}

// Shared error boundary for all (app) routes. Next bubbles a render/fetch error here.
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  // Read on the client only (null on the server and at hydration), so a recoverable expiry never
  // flashes the error and the server HTML still matches.
  const recoverable = useSyncExternalStore(noSubscribe, sessionRecoverable, () => null);

  useEffect(() => {
    // Surface for debugging; no PII in these errors.
    console.error(error);
    // Production redacts server error messages, so a 401 cannot be read from `error`; the session's
    // state is the signal. A full reload, not router.refresh() + reset(): reset re-rendered from the
    // payload that had already failed, so the error came straight back (seen in the browser).
    if (!recoverable) return;
    if (!accessTokenExpired()) {
      reloadOnce();
      return;
    }
    void refreshAccessToken().then((ok) => {
      if (ok) {
        reloadOnce();
      } else {
        expireSession();
        window.location.assign("/login");
      }
    });
  }, [error, recoverable]);

  if (recoverable !== false) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <div
        role="alert"
        className="rounded-xl border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] p-6"
      >
        <h1 className="text-title font-semibold text-danger">Something went wrong</h1>
        <p className="mt-1.5 text-body leading-relaxed text-muted">
          This screen failed to load. Your data and the evidence vault are unaffected — retry, or move to
          another screen.
        </p>
        <div className="mt-4">
          <Button variant="primary" onClick={reset}>Try again</Button>
        </div>
      </div>
    </div>
  );
}
