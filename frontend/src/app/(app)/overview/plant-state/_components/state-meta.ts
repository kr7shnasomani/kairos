import type { PlantOperatingState } from "@/lib/types";

export const STATE_META: Record<PlantOperatingState, { label: string; tone: "verified" | "caution" | "danger" | "neutral"; desc: string }> = {
  normal:      { label: "Normal",      tone: "verified", desc: "Full operations. All ingestion, briefs, and governors active." },
  turnaround:  { label: "Turnaround",  tone: "caution",  desc: "Planned maintenance. Brief cadence reduced; PTW governor exempt." },
  shutdown:    { label: "Shutdown",    tone: "caution",  desc: "Operations suspended. Safety interlocks remain active." },
  emergency:   { label: "Emergency",   tone: "danger",   desc: "Emergency state. Critical-only briefs; all non-safety automation paused." },
};

export const STATES: PlantOperatingState[] = ["normal", "turnaround", "shutdown", "emergency"];

/** Tone → CSS token name ("neutral" has no token; falls back to --muted). */
export function toneToken(tone: "verified" | "caution" | "danger" | "neutral"): string {
  return tone === "neutral" ? "muted" : tone;
}
