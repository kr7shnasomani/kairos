import type { AuthorityLevel, BriefPriority } from "./types";

/** Tiny classNames joiner — avoids a dependency for simple conditional classes. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Compact relative time, e.g. "2h ago". */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const min = Math.round(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

/** Current epoch ms. Lives here (not in render) so components stay pure — reading
 *  the clock during render is non-deterministic and hydration-unsafe. */
export function nowMs(): number {
  return Date.now();
}

/** SLA countdown label + tone class for a due timestamp. */
export function slaCountdown(sla_due_at: string, currentMs = nowMs()): { label: string; tone: string } {
  const hoursLeft = Math.floor((new Date(sla_due_at).getTime() - currentMs) / 3600000);
  const tone = hoursLeft < 4 ? "text-danger" : hoursLeft < 24 ? "text-caution" : "text-muted";
  const label = hoursLeft < 24 ? `${hoursLeft}h left` : `${Math.floor(hoursLeft / 24)}d left`;
  return { label, tone };
}

/** Compact "halted since" duration, e.g. "7h" / "2d". */
export function haltedDuration(since: string): string {
  const hrs = Math.round((Date.now() - new Date(since).getTime()) / 3600000);
  return hrs < 24 ? `${hrs}h` : `${Math.round(hrs / 24)}d`;
}

/** Whole hours a deadline is past (0 if not yet due). Keeps clock reads out of render. */
export function overdueHours(deadline: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(deadline).getTime()) / 3600000));
}

export interface PriorityMeta {
  label: string;
  /** CSS var color token name */
  color: string;
}

export function priorityMeta(p: BriefPriority): PriorityMeta {
  switch (p) {
    case "critical":
      return { label: "Critical", color: "var(--danger)" };
    case "high":
      return { label: "High", color: "var(--caution)" };
    case "normal":
      return { label: "Normal", color: "var(--muted)" };
    case "medium":
      return { label: "Medium", color: "var(--info)" };
    default:
      return { label: "Low", color: "var(--muted)" };
  }
}

const AUTHORITY_NAMES: Record<AuthorityLevel, string> = {
  1: "Regulation",
  2: "Standard",
  3: "OEM",
  4: "Site SOP",
  5: "Field",
};

// Display names for the provider keys the backend returns as `model` on every answer and uses as
// `/health/model?provider=` (backend: services/model_providers.py). One map, so the Copilot badge and
// System Health cannot name the same provider two ways. An unknown key is shown as-is.
const PROVIDER_NAMES: Record<string, string> = {
  tokenfactory: "Nebius Token Factory",
  nim: "NVIDIA NIM",
  openrouter: "OpenRouter",
  gemini: "Google Gemini",
  ollama: "Ollama (local)",
  jina: "Jina",
  groq: "Groq",
};

export function providerName(key: string): string {
  return PROVIDER_NAMES[key] ?? key;
}

export function authorityLabel(level: AuthorityLevel): string {
  return `L${level} · ${AUTHORITY_NAMES[level]}`;
}

// The five-level hierarchy from ARCHITECTURE.md (Layer 4). The short names above fit a badge; these
// say what each level actually is, for the badge's hover text.
const AUTHORITY_MEANINGS: Record<AuthorityLevel, string> = {
  1: "a regulatory requirement",
  2: "an engineering standard or site-specific policy",
  3: "an OEM manual or approved technical specification",
  4: "a site operating procedure or maintenance standard",
  5: "a field observation, informal note or unverified report",
};

/** One sentence explaining a level, including which way the scale runs. */
export function authorityDescription(level: AuthorityLevel): string {
  return `Authority level ${level} of 5, where 1 is highest: ${AUTHORITY_MEANINGS[level]}. When sources conflict, higher authority ranks first.`;
}

/** Criticality display — accepts both fixture (high/medium/low) and live
 *  (safety_critical/critical/non_critical) vocabularies. */
export function criticalityMeta(c: string): { label: string; color: string } {
  switch (c) {
    case "safety_critical":
    case "high":
      return { label: "Safety-critical", color: "var(--danger)" };
    case "critical":
    case "medium":
      return { label: "Critical", color: "var(--caution)" };
    case "non_critical":
    case "low":
      return { label: "Non-critical", color: "var(--muted)" };
    default:
      return { label: c, color: "var(--muted)" };
  }
}

/** Human label for a trigger_event_type like "work_order_created". */
export function triggerLabel(t: string): string {
  return t
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** First letter uppercased, rest unchanged. Safe on undefined/empty (live data can drift). */
export function capitalize(s?: string | null): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}
