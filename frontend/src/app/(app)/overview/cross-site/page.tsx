import Link from "next/link";
import { PageHeader } from "@/components/ui";

import { Icon } from "@/components/icon";
// Cross-site pattern detection has no backend: nothing correlates one site's failures with
// another's. We show an honest "unavailable" state rather than fabricated alerts.
export default function CrossSiteAlertsPage() {
  return (
    <div data-testid="cross-site-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/overview" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Overview
      </Link>

      <PageHeader
        className="mt-4"
        title="Cross-Site Pattern Alerts"
        lede="Failure patterns that repeat across more than one site, matched by statistical signature, so a precursor seen at one plant can warn the others before it escalates."
      />

      <div data-testid="cross-site-unavailable" className="mt-6 rounded-xl border border-line bg-surface p-10 text-center shadow-sm">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-2 text-muted">
          <Icon name="graph" size={22} />
        </div>
        <h2 className="mt-4 text-title font-semibold text-ink">Cross-site matching is not available yet</h2>
        <p className="mx-auto mt-2 max-w-xl text-body leading-relaxed text-muted">
          Cross-site pattern detection compares telemetry, inspection cadences, and failure histories across
          facilities. Kairos does not correlate sites yet, so no alerts are shown here. Each site&apos;s assets,
          documents and briefs are on their own pages, and matched precursors will appear here, each attributed
          to its originating site, once matching is built.
        </p>
      </div>
    </div>
  );
}
