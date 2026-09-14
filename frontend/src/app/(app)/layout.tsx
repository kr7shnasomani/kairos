import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";

// Authenticated, live-data routes render per request — never statically prerendered
// at build time (no backend then). Required now that fetchers are live-only: a
// server page's throw-on-fallback would otherwise fail the production build's SSG.
export const dynamic = "force-dynamic";

// Longest-prefix map — this is the ONLY title-setting mechanism for every page under
// (app), both on SSR/refresh and on client-side navigation (Next.js resolves
// generateMetadata on every transition, not just the first load; no page in this route
// group sets its own <title>, and AppShell doesn't either — a route missing from this
// list, or listed only under a shorter prefix, shows the wrong title in both cases,
// not just on refresh, which is how /system-benchmarks and /management/coverage were
// found and fixed 2026-08-24: the first had no entry at all (bare "Kairos"), the second
// fell through to the generic "/management" entry ("Kairos: Overview") because a
// specific one wasn't listed above it. `.find()` returns the first array match, so a
// specific prefix MUST be listed before any shorter prefix it also satisfies.
const ROUTE_LABELS: [string, string][] = [
  ["/briefs", "Briefs"],
  ["/copilot", "Copilot"],
  ["/assets/register", "Register Assets"],
  ["/assets/bootstrap", "Identity Confirmation"],
  ["/assets", "Assets"],
  ["/events", "Events"],
  ["/rca", "RCA"],
  ["/graph", "Graph"],
  ["/audit", "Audit Trail"],
  ["/projects", "Projects"],
  ["/management/cross-site", "Cross-Site Patterns"],
  ["/management/plant-state", "Plant State"],
  ["/management/coverage", "Coverage"],
  ["/management", "Overview"],
  ["/system-benchmarks", "System Benchmarks"],
  ["/documents/ingest", "Document Ingest"],
  ["/documents/compare", "Document Compare"],
  ["/documents", "Documents"],
  ["/offboarding", "Off-Boarding"],
  ["/settings", "System Settings"],
  ["/system-health", "System Health"],
  ["/system-information", "System Information"],
  ["/field/voice", "Voice Note"],
  ["/field/deviation", "Deviation Flag"],
  ["/field/elicitation", "Knowledge Capture"],
  ["/compliance/audit-pack", "Audit Pack"],
  ["/compliance/nonconformance", "Non-Conformances"],
  ["/compliance", "Compliance"],
  ["/governance/conflicts", "Conflicts"],
  ["/governance/quarantine", "Quarantine"],
  ["/governance/moc", "Management of Change"],
  ["/governance/sla", "SLA Report"],
  ["/governance/circuit-breaker", "Circuit Breaker"],
  ["/governance/model-gate", "Model Gate"],
  ["/governance/timestamp-drift", "Timestamp Drift"],
  ["/governance/push-volume-gate", "Push-Volume Gate"],
  ["/governance", "Governance"],
];

export async function generateMetadata(): Promise<Metadata> {
  const { headers } = await import("next/headers");
  const heads = await headers();
  const pathname = heads.get("x-pathname") ?? "";
  const label = ROUTE_LABELS.find(
    ([prefix]) => pathname === prefix || pathname.startsWith(prefix + "/"),
  )?.[1];
  return { title: label ? `Kairos: ${label}` : "Kairos" };
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
