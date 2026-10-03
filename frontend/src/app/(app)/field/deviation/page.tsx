"use client";

// Field form to flag a physical deviation from the P&ID — freezes briefs for the asset.
import { useState } from "react";
import { postDeviationFlag } from "@/lib/api";
import { Button, PageHeader } from "@/components/ui";

import { Icon } from "@/components/icon";
type Stage = "form" | "submitting" | "done" | "error";

export default function DeviationPage() {
  const [stage, setStage] = useState<Stage>("form");
  const [assetId, setAssetId] = useState("");
  const [description, setDescription] = useState("");
  const [topology, setTopology] = useState("");
  const [eventId, setEventId] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!assetId.trim() || !description.trim()) return;
    setStage("submitting");
    try {
      const ev = await postDeviationFlag({
        asset_id: assetId.trim(),
        description: description.trim(),
        affected_topology_path: topology.trim() || undefined,
      });
      setEventId(ev.event_id);
      setStage("done");
    } catch {
      setStage("error");
    }
  }

  if (stage === "done") {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-line bg-surface px-5 py-8 text-center shadow-sm sm:px-8">
        <div className="mx-auto grid size-14 place-items-center rounded-full bg-[color-mix(in_srgb,var(--caution)_14%,transparent)]">
          <Icon name="warning" className="size-7 text-caution" />
        </div>
        <h1 className="mt-4 text-title font-semibold">Deviation flag raised</h1>
        {eventId && (
          <p className="mt-1 text-caption text-muted">
            Event <span className="tabular font-medium text-ink">{eventId}</span>
          </p>
        )}
        <p className="mt-3 text-body leading-relaxed text-muted">
          Briefs for asset{" "}
          <span className="font-semibold text-ink">{assetId}</span> are now frozen
          pending engineering review. An engineer must resolve this flag before normal brief
          delivery resumes.
        </p>
      </div>
    );
  }

  return (
    <>
    <div data-testid="deviation-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        className="mb-6"
        title="Physical Deviation Flag"
        lede="Flag a physical condition that deviates from the P&ID or procedure. Briefs for the affected asset will be frozen until an engineer reviews and resolves this flag."
      />

      <div data-testid="deviation-layout" className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <form data-testid="deviation-form" onSubmit={submit} className="flex min-w-0 flex-col gap-5 rounded-2xl border border-line bg-surface p-4 shadow-sm sm:p-6" noValidate>
        <div>
          <label htmlFor="asset-id" className="block text-body font-semibold">
            Asset / tag number <span aria-hidden="true" className="text-danger">*</span>
          </label>
          <input
            id="asset-id"
            type="text"
            value={assetId}
            onChange={(e) => setAssetId(e.target.value)}
            placeholder="e.g. P-101"
            required
            aria-required="true"
            className="mt-1.5 min-h-[52px] w-full rounded-xl border border-line bg-surface-2 px-4 text-sm outline-none transition-colors focus-visible:border-accent"
          />
        </div>

        <div>
          <label htmlFor="description" className="block text-body font-semibold">
            Description of deviation <span aria-hidden="true" className="text-danger">*</span>
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what you observed that deviates from the expected state…"
            rows={4}
            required
            aria-required="true"
            className="mt-1.5 w-full resize-none rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm leading-relaxed outline-none transition-colors focus-visible:border-accent"
          />
        </div>

        <div>
          <label htmlFor="topology" className="block text-body font-semibold">
            Affected topology path{" "}
            <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="topology"
            type="text"
            value={topology}
            onChange={(e) => setTopology(e.target.value)}
            placeholder="e.g. P-101 → suction valve → isolation boundary"
            className="mt-1.5 min-h-[52px] w-full rounded-xl border border-line bg-surface-2 px-4 text-sm outline-none transition-colors focus-visible:border-accent"
          />
        </div>

        {stage === "error" && (
          <p role="alert" className="text-body text-danger">
            Submission failed. Check your connection and try again.
          </p>
        )}

        <div className="mt-2">
          <Button
            type="submit"
            variant="danger"
            disabled={!assetId.trim() || !description.trim() || stage === "submitting"}
            className="h-[52px] w-full text-subtitle"
          >
            {stage === "submitting" ? "Raising flag…" : "Raise deviation flag"}
          </Button>
          <p className="mt-2 text-center text-caption text-muted">
            This action freezes briefs for the asset until engineering resolves the flag.
          </p>
        </div>
      </form>

      <aside data-testid="deviation-context" className="rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-6">
        <p className="text-label font-bold uppercase tracking-[0.1em] text-caution">What happens next</p>
        <ol className="mt-4 space-y-4 text-caption text-muted">
          <li><span className="font-semibold text-ink">Brief delivery freezes</span><br />New briefs for the tagged asset are held to prevent stale guidance.</li>
          <li><span className="font-semibold text-ink">Engineering investigates</span><br />The physical condition is compared with the governed P&amp;ID and procedure.</li>
          <li><span className="font-semibold text-ink">Resolution is audited</span><br />Normal delivery resumes only after the deviation is resolved.</li>
        </ol>
        <p className="mt-4 border-t border-line pt-4 text-caption text-muted">Describe only what you observed. Include the topology path when it helps locate the condition.</p>
      </aside>
      </div>
    </div>
    </>
  );
}
