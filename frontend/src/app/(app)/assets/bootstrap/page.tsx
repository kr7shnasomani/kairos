"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  confirmAlias,
  confirmAssetIdentity,
  getAliasCandidates,
  getProvisionalAssets,
  rejectAlias,
  type AliasCandidate,
  type ProvisionalAsset,
} from "@/lib/api";
import { getMe } from "@/lib/auth";
import { useFetch } from "@/lib/use-fetch";
import { Button, StatusBadge, EmptyState, PageHeader } from "@/components/ui";
import { PageSkeleton } from "@/components/skeleton";
import { MDM_ROLES } from "../identity-action";

// Both queues are live: provisional records are `assets` rows with no confirmed identity, and alias
// candidates are the extraction pipeline's unconfirmed `asset_alias_map` proposals. This page used to
// render three hardcoded provisional assets and two aliases whose Confirm/Reject changed nothing.
// Registering new assets lives on its own page, /assets/register.
export default function BootstrapPage() {
  const [canConfirm, setCanConfirm] = useState(false);
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<string>("");
  const [reload, setReload] = useState(0);
  const provisional = useFetch(getProvisionalAssets, [reload]);
  const aliases = useFetch(getAliasCandidates, [reload]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe().then((u) => {
      setCanConfirm(!!u && MDM_ROLES.includes(u.role));
      if (u) setMe(u.user_id);
      setReady(true);
    });
  }, []);

  async function run(key: string, mutate: () => Promise<unknown>, failure: string) {
    setBusy(key);
    setError(null);
    try {
      await mutate();
      setReload((r) => r + 1);
    } catch {
      setError(failure);
    } finally {
      setBusy(null);
    }
  }

  function confirm(p: ProvisionalAsset) {
    return run(
      p.asset_id,
      () =>
        confirmAssetIdentity({
          asset_id: p.asset_id,
          tag_number: p.tag_number || p.asset_id,
          name: p.name,
          equipment_class: p.equipment_class,
          criticality: p.criticality,
          site_id: p.site_id,
          facility_id: p.facility_id,
          // The API records the confirmer from the session; this satisfies the required field.
          confirmed_by_user_id: me,
        }),
      "Identity confirmation was not saved. Check the connection and try again.",
    );
  }

  function decideAlias(a: AliasCandidate, accept: boolean) {
    return run(
      `alias:${a.alias}`,
      () => (accept ? confirmAlias(a.canonical_asset_id, a.alias) : rejectAlias(a.canonical_asset_id, a.alias)),
      `Could not ${accept ? "confirm" : "reject"} alias ${a.alias}. Try again.`,
    );
  }

  if (!ready) return <PageSkeleton />;

  const provisionalItems = provisional.status === "live" ? provisional.data : [];
  const aliasItems = aliases.status === "live" ? aliases.data : [];

  return (
    <div data-testid="identity-workspace" className="mx-auto max-w-5xl">
      <Link href="/assets" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Assets
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Layer 1 · Master data management"
        title="Asset identity confirmation"
        lede="Review provisional equipment records and approve only identities that belong to a canonical asset."
      />

      <div data-testid="identity-guardrail" className="mt-5 flex gap-3 rounded-xl border border-line bg-surface p-4 shadow-sm">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-[color-mix(in_srgb,var(--caution)_14%,transparent)] text-caution" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3l7 3v5c0 4.6-2.9 8.1-7 10-4.1-1.9-7-5.4-7-10V6l7-3z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
        </span>
        <div className="min-w-0">
          <p className="text-body font-semibold text-ink">Human confirmation required</p>
          <p className="mt-0.5 max-w-3xl text-caption leading-relaxed text-muted">
            Extracted knowledge remains quarantined until a qualified user confirms its asset identity. Kairos never invents the missing identity.
          </p>
        </div>
      </div>

      {!canConfirm && (
        <div className="mt-6 rounded-xl border border-line bg-surface p-5 text-body text-muted">
          Identity confirmation requires the <span className="font-semibold text-ink">engineer</span> or <span className="font-semibold text-ink">admin</span> role.
        </div>
      )}

      {canConfirm && (
        <div className="mt-6 space-y-6">
          {error && <p role="alert" className="rounded-lg border border-line px-4 py-3 text-body text-danger">{error}</p>}

          <section data-testid="provisional-queue" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-4 sm:px-5">
              <div>
                <h2 className="text-sm font-semibold text-ink">Provisional assets</h2>
                <p className="mt-0.5 text-caption text-muted">Records awaiting a canonical identity.</p>
              </div>
              <StatusBadge tone={provisionalItems.length ? "caution" : "verified"} dot={false}>
                {provisionalItems.length} pending
              </StatusBadge>
            </div>
            <div className="divide-y divide-line">
              {provisional.status === "loading" && <p className="p-4 text-body text-muted sm:p-5">Loading provisional records…</p>}
              {provisional.status === "error" && (
                <div className="flex items-center justify-between gap-3 p-4 sm:p-5">
                  <p className="text-body text-muted">Could not load provisional records.</p>
                  <Button variant="ghost" onClick={provisional.retry}>Retry</Button>
                </div>
              )}
              {provisional.status === "live" && provisionalItems.length === 0 && (
                <div className="p-4 sm:p-5"><EmptyState message="Every registered asset has a confirmed identity." /></div>
              )}
              {provisionalItems.map((p) => (
                <div
                  key={p.asset_id}
                  data-testid={`provisional-${p.asset_id}`}
                  className="grid gap-3 px-4 py-4 transition-colors hover:bg-surface-2 md:grid-cols-[minmax(0,1fr)_minmax(150px,0.55fr)_auto] md:items-center sm:px-5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="tabular text-body font-semibold text-accent">{p.asset_id}</span>
                      <StatusBadge tone="caution" dot={false}>provisional</StatusBadge>
                    </div>
                    <p className="mt-1 truncate text-caption font-medium text-ink">{p.name}</p>
                  </div>
                  <div className="min-w-0 text-label text-muted">
                    <p className="truncate font-medium text-ink">{p.equipment_class.replaceAll("_", " ")}</p>
                    <p className="mt-0.5 truncate">Source · {(p.eam_source || "manual").replaceAll("_", " ")}</p>
                  </div>
                  <Button className="h-11 w-full md:h-9 md:w-auto" variant="primary" disabled={busy === p.asset_id || !me} onClick={() => confirm(p)}>
                    {busy === p.asset_id ? "Confirming…" : "Confirm identity"}
                  </Button>
                </div>
              ))}
            </div>
          </section>

          <section data-testid="alias-queue" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-4 sm:px-5">
              <div>
                <h2 className="text-sm font-semibold text-ink">Unresolved tag aliases</h2>
                <p className="mt-0.5 text-caption text-muted">Tags extraction found in documents, proposed as another name for an asset.</p>
              </div>
              <StatusBadge tone={aliasItems.length ? "info" : "verified"} dot={false}>
                {aliasItems.length} pending
              </StatusBadge>
            </div>
            <div className="divide-y divide-line">
              {aliases.status === "loading" && <p className="p-4 text-body text-muted sm:p-5">Loading alias candidates…</p>}
              {aliases.status === "error" && (
                <div className="flex items-center justify-between gap-3 p-4 sm:p-5">
                  <p className="text-body text-muted">Could not load alias candidates.</p>
                  <Button variant="ghost" onClick={aliases.retry}>Retry</Button>
                </div>
              )}
              {aliases.status === "live" && aliasItems.length === 0 && (
                <div className="p-4 sm:p-5"><EmptyState message="No pending aliases." /></div>
              )}
              {aliasItems.map((a) => {
                const key = `alias:${a.alias}`;
                return (
                  <div key={a.alias} className="grid gap-3 px-4 py-4 transition-colors hover:bg-surface-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center sm:px-5">
                    <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] sm:items-center">
                      <div className="min-w-0">
                        <p className="text-label text-muted">Observed tag</p>
                        <p className="tabular mt-0.5 truncate text-caption font-semibold text-ink">{a.alias}</p>
                      </div>
                      <span className="hidden text-muted sm:block" aria-hidden="true">→</span>
                      <div className="min-w-0">
                        <p className="text-label text-muted">Canonical asset</p>
                        <p className="tabular mt-0.5 truncate text-caption font-semibold text-accent">{a.canonical_asset_id}</p>
                      </div>
                      <StatusBadge tone="info" dot={false}>{Math.round(a.confidence * 100)}% match</StatusBadge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 md:flex">
                      <Button variant="ghost" className="h-11 md:h-9" disabled={busy === key} aria-label={`Confirm alias ${a.alias}`} onClick={() => decideAlias(a, true)}>Confirm</Button>
                      <Button variant="ghost" className="h-11 text-danger md:h-9" disabled={busy === key} aria-label={`Reject alias ${a.alias}`} onClick={() => decideAlias(a, false)}>Reject</Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
