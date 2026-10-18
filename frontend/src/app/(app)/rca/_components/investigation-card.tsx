import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui-card";
import type { RcaStep } from "@/lib/types";

const TOOL_LABEL: Record<string, string> = {
  failure_history: "Failure history",
  sister_assets: "Sister equipment",
  asset_knowledge: "Knowledge graph",
  pending_changes: "Pending changes",
  search_documents: "Document search",
  field_notes: "Field notes",
};

/** The lookups the investigation chose, in order: what it looked at, why, and what it found. */
export function InvestigationCard({ steps }: { steps: RcaStep[] }) {
  if (steps.length === 0) return null;
  return (
    <Card className="overflow-hidden shadow-sm">
      <CardHeader className="border-b border-line p-4 sm:px-5">
        <CardTitle className="text-sm">Investigation</CardTitle>
        <CardDescription>What the system chose to look up beyond the 90-day timeline, and why.</CardDescription>
      </CardHeader>
      <ol className="divide-y divide-line">
        {steps.map((s, i) => (
          <li key={`${s.tool}-${i}`} className="flex gap-3 p-4 sm:px-5">
            <span className="tabular pt-0.5 text-label font-bold text-muted">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-body font-semibold text-ink">{TOOL_LABEL[s.tool] ?? s.tool}</p>
              {s.why && <p className="mt-0.5 text-caption leading-relaxed text-muted text-pretty">{s.why}</p>}
              <p className="mt-1 text-caption text-ink">{s.found}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
