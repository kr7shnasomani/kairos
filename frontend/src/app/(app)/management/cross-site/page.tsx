import Link from "next/link";
import { PageHeader } from "@/components/ui";

import { Icon } from "@/components/icon";
// Cross-site pattern detection needs ≥2 facilities on the control plane. This is a
// single-site deployment, so there is genuinely nothing to correlate — we show an
// honest "unavailable" state rather than fabricated alerts.
export default function CrossSiteAlertsPage() {
  return (
    <div data-testid="cross-site-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/management" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Overview
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Overview"
        title="Cross-site pattern alerts"
        lede="Statistical signatures matched across sites — recurring failure precursors surfaced before they escalate."
      />

      <div data-testid="cross-site-unavailable" className="mt-6 rounded-xl border border-line bg-surface p-10 text-center shadow-sm">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-2 text-muted">
          <Icon name="graph" size={22} />
        </div>
        <h2 className="mt-4 text-title font-semibold text-ink">No cross-site data in this deployment</h2>
        <p className="mx-auto mt-2 max-w-xl text-body leading-relaxed text-muted">
          Cross-site pattern detection compares telemetry, inspection cadences, and failure histories across
          multiple facilities. This is a single-site deployment, so there is nothing to correlate yet. When a
          second site is connected to the control plane, matched precursors will appear here — each attributed to
          its originating site.
        </p>
      </div>
    </div>
  );
}
