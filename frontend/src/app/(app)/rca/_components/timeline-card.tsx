"use client";

import { Timeline, type TimelineEvent } from "@/components/ui";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui-card";
import type { RcaPack } from "@/lib/types";

const SOURCE_TONE: Record<string, TimelineEvent["tone"]> = {
  neo4j: "verified",
  historian: "info",
  operational_events: "neutral",
  quarantine: "caution",
};

const SOURCE_LABEL: Record<string, string> = {
  neo4j: "graph",
  historian: "telemetry",
  operational_events: "plant events",
  quarantine: "unverified",
};

function toTimelineEvents(pack: RcaPack): TimelineEvent[] {
  return (pack.timeline ?? []).map((e, i) => ({
    id: `${e.event_type}-${i}`,
    timestamp: new Date(e.occurred_at).toLocaleString("en-GB", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    }),
    label: e.event_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    description: e.description,
    tone: SOURCE_TONE[e.source] ?? "neutral",
    meta: SOURCE_LABEL[e.source] ?? e.source,
  }));
}

/** Chronological evidence spine for the investigation pack. */
export function TimelineCard({ pack }: { pack: RcaPack }) {
  return (
    <Card className="overflow-hidden shadow-sm">
      <CardHeader className="border-b border-line p-4 sm:px-5">
        <CardTitle className="text-sm">Timeline</CardTitle>
        <CardDescription>Connected evidence ordered around the incident.</CardDescription>
      </CardHeader>
      <div className="p-4 sm:p-5"><Timeline events={toTimelineEvents(pack)} /></div>
    </Card>
  );
}
