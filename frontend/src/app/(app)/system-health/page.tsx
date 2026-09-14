"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getHealthDetailed, getOtConnectors, probeEndpoint, probeModel, type OtConnectorRegistry, type ProbeResult, type ModelProbe } from "@/lib/api";
import { getMe } from "@/lib/auth";
import { ADMIN_ROLES } from "@/components/use-role";
import { PageHeader, StatusBadge } from "@/components/ui";
import { SystemTabs } from "@/components/system-tabs";
import { Skeleton } from "@/components/skeleton";
import { capitalize, cn } from "@/lib/utils";
import { fmtRelTime } from "@/lib/format";
import type { HealthDetailed, ServiceHealth } from "@/lib/types";

// Cheap DB-read probes poll at 30s (13 req/cycle ≈ 26/min, far under the 120/min rate limit).
const POLL_MS = 30000;
// Model providers are rate-limited (each probe spends quota) — opt-in, and only once/minute when on.
const MODEL_POLL_MS = 60000;
const MODELS_LS_KEY = "kairos-health-models";

// Every API surface (docs/API.md) with a cheap, side-effect-free read-only GET we probe live.
// Search is NOT here: it embeds via Jina on every call (rate-limited) → covered by the Jina toggle.
const API_GROUPS: { group: string; layer: string; endpoint: string; probe: string }[] = [
  { group: "Health", layer: "Liveness", endpoint: "GET /health", probe: "/health/" },
  { group: "Authentication", layer: "Auth", endpoint: "GET /auth/me", probe: "/auth/me" },
  { group: "Assets", layer: "L1 · MDM", endpoint: "GET /assets", probe: "/assets/?limit=1" },
  { group: "Documents", layer: "L2–3 · Vault", endpoint: "GET /documents", probe: "/documents/?limit=1" },
  { group: "Events", layer: "L8 · Operational", endpoint: "GET /events/plant-state", probe: "/events/plant-state/SITE_001" },
  { group: "Briefs", layer: "L8 · Delivery", endpoint: "GET /briefs/governor/status", probe: "/briefs/governor/status" },
  { group: "Governance", layer: "L7", endpoint: "GET /governance/circuit-breaker", probe: "/governance/circuit-breaker" },
  { group: "Compliance", layer: "Compliance", endpoint: "GET /compliance/frameworks", probe: "/compliance/frameworks" },
  { group: "Elicitation", layer: "L6", endpoint: "GET /elicitation/offboarding", probe: "/elicitation/offboarding" },
  { group: "Annotations", layer: "L3", endpoint: "GET /annotations/stats", probe: "/annotations/stats" },
  { group: "Audit Log", layer: "Governance", endpoint: "GET /audit-log", probe: "/audit-log/?limit=1" },
];

// Rate-limited external model providers — opt-in monitoring only.
const MODELS: { key: string; name: string; sub: string }[] = [
  { key: "nim", name: "NVIDIA NIM", sub: "LLM synthesis · nemotron-3-super-120b" },
  { key: "gemini", name: "Google Gemini", sub: "LLM fallback · gemini-2.5-flash-lite" },
  { key: "jina", name: "Jina", sub: "Embeddings · powers Search & RAG" },
  { key: "groq", name: "Groq", sub: "Whisper STT · voice notes" },
];

const TONE = { healthy: "verified", degraded: "caution", down: "danger" } as const;
// `idle` is "we are not measuring this", NOT a health state. It exists because monitoring is
// opt-in: rendering the off state as `degraded` gave every un-monitored provider a pulsing amber
// dot identical to a real outage, so a freshly-loaded page looked like four dead providers.
const DOT = { healthy: "bg-verified", degraded: "bg-caution", down: "bg-danger", idle: "bg-muted" } as const;
const STORE_RANK: Record<ServiceHealth["status"], number> = { down: 0, degraded: 1, healthy: 2 };
const CONNECTOR_TONE = { active: "verified", not_configured: "neutral", registered: "info" } as const;
const CONNECTOR_LABEL: Record<string, string> = { active: "Active", not_configured: "Not configured", registered: "Registered" };

type ProbeRow = (typeof API_GROUPS)[number] & { result?: ProbeResult };

function StatusDot({ tone }: { tone: keyof typeof DOT }) {
  // Only a measured non-healthy state pulses. `idle` must stay still — an animated dot reads as
  // "something needs attention", which is exactly the wrong claim for a provider nobody is probing.
  const pulses = tone !== "healthy" && tone !== "idle";
  return <span className={cn("size-2 shrink-0 rounded-full", DOT[tone], pulses && "animate-pulse")} aria-hidden="true" />;
}

function Toggle({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150 ease-out",
        on ? "bg-accent" : "bg-surface-2 border border-line",
      )}
    >
      <span className={cn("inline-block size-3.5 rounded-full bg-canvas shadow-sm transition-transform duration-150 ease-out", on ? "translate-x-[18px]" : "translate-x-[3px]")} />
    </button>
  );
}

export default function SystemHealthPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [stores, setStores] = useState<HealthDetailed | null>(null);
  // `undefined` = not loaded yet; `null` = the connector service is unreachable (a real state).
  const [connectors, setConnectors] = useState<OtConnectorRegistry | null | undefined>(undefined);
  const [apis, setApis] = useState<ProbeRow[]>(API_GROUPS);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const runRef = useRef<() => void>(() => {});

  // Model monitoring is opt-in and persisted per browser (read once via lazy init).
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() => {
    if (typeof window === "undefined") return {};
    try { const raw = localStorage.getItem(MODELS_LS_KEY); return raw ? JSON.parse(raw) : {}; } catch { return {}; }
  });
  const [modelResults, setModelResults] = useState<Record<string, ModelProbe>>({});
  const [modelBusy, setModelBusy] = useState<Record<string, boolean>>({});
  const modelTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Admin-only.
  useEffect(() => {
    let alive = true;
    getMe().then((u) => {
      if (!alive) return;
      const ok = !!u && ADMIN_ROLES.includes(u.role);
      setAuthorized(ok);
      if (!ok) router.replace(u?.role === "field_worker" ? "/briefs" : "/management");
    });
    return () => { alive = false; };
  }, [router]);

  // Always-on cheap probes.
  useEffect(() => {
    if (!authorized) return;
    let alive = true;
    const load = async () => {
      setRefreshing(true);
      const [health, results, registry] = await Promise.all([
        getHealthDetailed(),
        Promise.all(API_GROUPS.map((g) => probeEndpoint(g.probe))),
        getOtConnectors().then((r) => r.data).catch(() => null),
      ]);
      if (!alive) return;
      setStores(health.data);
      setConnectors(registry);
      setApis(API_GROUPS.map((g, i) => ({ ...g, result: results[i] })));
      setCheckedAt(new Date().toISOString());
      setLoading(false);
      setRefreshing(false);
    };
    runRef.current = () => { void load(); };
    void load();
    timer.current = setInterval(() => { void load(); }, POLL_MS);
    return () => { alive = false; if (timer.current) clearInterval(timer.current); };
  }, [authorized]);

  // Opt-in model probes: probe enabled providers now, then every 60s.
  useEffect(() => {
    if (!authorized) return;
    let alive = true;
    const on = MODELS.filter((m) => enabled[m.key]).map((m) => m.key);
    if (on.length === 0) return;
    const probe = async () => {
      setModelBusy((b) => ({ ...b, ...Object.fromEntries(on.map((k) => [k, true])) }));
      const results = await Promise.all(on.map((k) => probeModel(k)));
      if (!alive) return;
      setModelResults((r) => ({ ...r, ...Object.fromEntries(on.map((k, i) => [k, results[i]])) }));
      setModelBusy((b) => ({ ...b, ...Object.fromEntries(on.map((k) => [k, false])) }));
    };
    void probe();
    modelTimer.current = setInterval(() => { void probe(); }, MODEL_POLL_MS);
    return () => { alive = false; if (modelTimer.current) clearInterval(modelTimer.current); };
  }, [authorized, enabled]);

  function toggleModel(key: string) {
    setEnabled((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try { localStorage.setItem(MODELS_LS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      if (!next[key]) setModelResults((r) => { const copy = { ...r }; delete copy[key]; return copy; });
      return next;
    });
  }

  if (authorized === null || authorized === false) return null;

  const services = [...(stores?.services ?? [])].sort((a, b) => STORE_RANK[a.status] - STORE_RANK[b.status]);
  const apiUp = apis.filter((a) => a.result?.ok).length;
  const storesUp = services.filter((s) => s.status === "healthy").length;
  const allUp = !loading && apiUp === apis.length && stores?.overall === "healthy";
  const overall: keyof typeof TONE = loading ? "degraded" : allUp ? "healthy" : "degraded";

  return (
    <div className="w-full">
      <SystemTabs />
      <PageHeader
        eyebrow="Infrastructure"
        title="System Health"
        lede="Live status of every API surface and datastore, grouped by domain. Auto-refreshes every 30 seconds."
        actions={
          <button
            type="button"
            onClick={() => runRef.current()}
            disabled={refreshing}
            className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-caption font-semibold text-ink transition-[transform,background-color] duration-150 ease-out hover:bg-surface-2 active:scale-[0.97] disabled:opacity-60"
          >
            <svg className={cn("size-3.5", refreshing && "animate-spin")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6" />
            </svg>
            {refreshing ? "Checking…" : "Refresh"}
          </button>
        }
      />

      {/* Overall banner — the at-a-glance answer */}
      <div
        className={cn(
          "mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4",
          overall === "healthy"
            ? "border-[color-mix(in_srgb,var(--verified)_35%,var(--line))] bg-[color-mix(in_srgb,var(--verified)_7%,var(--surface))]"
            : "border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_7%,var(--surface))]",
        )}
      >
        <div className="flex items-center gap-3">
          <StatusDot tone={overall} />
          <p className="text-body font-semibold text-ink">
            {loading ? "Checking all systems…" : allUp ? "All systems operational" : "Attention needed — one or more checks are failing"}
          </p>
        </div>
        <div className="flex items-center gap-4 text-caption text-muted">
          <span className="tabular font-medium">{apiUp}/{apis.length} APIs</span>
          <span className="tabular font-medium">{storesUp}/{services.length || 5} datastores</span>
          {checkedAt && <span>Checked {fmtRelTime(checkedAt)}</span>}
        </div>
      </div>

      {/* Two full-width columns on wide screens */}
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.7fr_1fr]">
        {/* API surfaces */}
        <section>
          <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">API surfaces</h2>
          <div className="mt-3 overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-label uppercase tracking-wide text-muted">
                  <th scope="col" className="px-4 py-2.5 font-semibold">Domain</th>
                  <th scope="col" className="hidden px-4 py-2.5 font-semibold sm:table-cell">Endpoint</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-semibold">Latency</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: API_GROUPS.length }).map((_, i) => (
                      <tr key={i} className="border-b border-line last:border-0">
                        <td className="px-4 py-3" colSpan={4}><Skeleton className="h-5 w-full rounded" /></td>
                      </tr>
                    ))
                  : apis.map((a) => {
                      const ok = a.result?.ok ?? false;
                      return (
                        <tr key={a.group} className="border-b border-line last:border-0">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2.5">
                              <StatusDot tone={ok ? "healthy" : "down"} />
                              <div className="min-w-0">
                                <p className="truncate text-body font-medium text-ink">{a.group}</p>
                                <p className="truncate text-label text-muted">{a.layer}</p>
                              </div>
                            </div>
                          </td>
                          <td className="hidden px-4 py-3 sm:table-cell"><code className="text-caption text-muted">{a.endpoint}</code></td>
                          <td className="px-4 py-3 text-right">
                            {a.result && a.result.status !== 0
                              ? <span className="tabular text-caption text-muted">{Math.round(a.result.latencyMs)} ms</span>
                              : <span className="text-caption text-muted">—</span>}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <StatusBadge tone={ok ? "verified" : "danger"}>
                              {ok ? "OK" : a.result?.status ? `HTTP ${a.result.status}` : "Unreachable"}
                            </StatusBadge>
                          </td>
                        </tr>
                      );
                    })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-label text-muted">Search &amp; retrieval run on Jina embeddings + the datastores below — monitor them in AI models.</p>
        </section>

        {/* Datastores */}
        <section>
          <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">Datastores &amp; dependencies</h2>
          <div className="mt-3 overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-label uppercase tracking-wide text-muted">
                  <th scope="col" className="px-4 py-2.5 font-semibold">Service</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="border-b border-line last:border-0">
                        <td className="px-4 py-3" colSpan={2}><Skeleton className="h-5 w-full rounded" /></td>
                      </tr>
                    ))
                  : services.length === 0
                    ? <tr><td className="px-4 py-4 text-caption text-muted" colSpan={2}>Live datastore status is unavailable.</td></tr>
                    : services.map((s) => (
                        <tr key={s.name} className="border-b border-line last:border-0">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2.5">
                              <StatusDot tone={s.status} />
                              <div className="min-w-0">
                                <p className="truncate text-body font-medium text-ink">{s.name}</p>
                                {s.details && <p className="truncate text-label text-danger" title={s.details}>{s.details}</p>}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <StatusBadge tone={TONE[s.status]}>{capitalize(s.status)}</StatusBadge>
                          </td>
                        </tr>
                      ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* OT historian connectors (Layer 5) — what this deployment can read telemetry from */}
      <section data-testid="ot-connectors" className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">OT historian connectors</h2>
          {connectors && <p className="tabular text-label text-muted">{connectors.active_count} of {connectors.connectors.length} active</p>}
        </div>
        {connectors === undefined ? (
          <Skeleton className="mt-3 h-24 w-full rounded-xl" />
        ) : connectors === null ? (
          <p className="mt-3 rounded-xl border border-line bg-surface p-4 text-caption text-danger">
            The OT connector service is unreachable, so the connector registry is unavailable.
          </p>
        ) : (
          <>
            <div className="mt-3 overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-line bg-surface-2 text-label uppercase tracking-wide text-muted">
                    <th scope="col" className="px-4 py-2.5 font-semibold">Connector</th>
                    <th scope="col" className="hidden px-4 py-2.5 font-semibold md:table-cell">Configured by</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {connectors.connectors.map((c) => (
                    <tr key={c.name} className="border-b border-line last:border-0">
                      <td className="px-4 py-3">
                        <p className="text-body font-medium text-ink">{c.name}</p>
                        <p className="text-label text-muted">{c.protocol}{c.detail ? ` · ${c.detail}` : ""}</p>
                      </td>
                      <td className="hidden px-4 py-3 md:table-cell"><code className="text-caption text-muted">{c.config_var}</code></td>
                      <td className="px-4 py-3 text-right">
                        <StatusBadge tone={CONNECTOR_TONE[c.status as keyof typeof CONNECTOR_TONE] ?? "neutral"}>{CONNECTOR_LABEL[c.status] ?? c.status}</StatusBadge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {connectors.serving_historian.note && (
              <p className="mt-2 text-label text-muted">
                {connectors.serving_historian.mock ? "Telemetry is served by the mock historian — " : ""}{connectors.serving_historian.note}
              </p>
            )}
          </>
        )}
      </section>

      {/* AI models & rate-limited services — opt-in */}
      <section className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">AI models &amp; rate-limited services</h2>
          <p className="text-label text-muted">Off by default — each probe spends provider quota. When on, checks once per minute.</p>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {MODELS.map((m) => {
            const on = !!enabled[m.key];
            const res = modelResults[m.key];
            const busy = !!modelBusy[m.key];
            return (
              <div key={m.key} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4">
                <div className="flex min-w-0 items-center gap-2.5">
                  <StatusDot tone={!on ? "idle" : res?.ok ? "healthy" : busy ? "degraded" : "down"} />
                  <div className="min-w-0">
                    <p className="truncate text-body font-medium text-ink">{m.name}</p>
                    <p className="truncate text-label text-muted">{m.sub}</p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {on && (
                    busy
                      ? <span className="text-caption text-muted">Checking…</span>
                      : res
                        ? <>
                            {res.latencyMs != null && <span className="tabular text-caption text-muted">{res.latencyMs} ms</span>}
                            <StatusBadge tone={res.ok ? "verified" : "danger"}>{res.ok ? "OK" : res.detail === "not configured" ? "No key" : "Down"}</StatusBadge>
                          </>
                        : <span className="text-caption text-muted">—</span>
                  )}
                  {!on && <span className="text-caption text-muted">Monitoring off</span>}
                  <Toggle on={on} onClick={() => toggleModel(m.key)} label={`Monitor ${m.name}`} />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
