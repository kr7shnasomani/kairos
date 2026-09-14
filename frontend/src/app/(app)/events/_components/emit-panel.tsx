"use client";

import { useState } from "react";
import { postAlarm, postInspectionComplete, postPtw, postShiftHandover, postTagOut, postWorkOrder } from "@/lib/api";
import { Button } from "@/components/ui";

// Work order and PTW are the two headline flows (a technician's brief; a permit that needs two
// signatures). The panel used to offer only tag-out, inspection, alarm and handover, so neither could
// be started from the UI — only the demo loader could trigger them.
const EMIT_TYPES = [
  { key: "work-order", label: "Work order" },
  { key: "ptw", label: "Permit to work" },
  { key: "tag-out", label: "Tag-out" },
  { key: "inspection-complete", label: "Inspection" },
  { key: "alarm", label: "Alarm" },
  { key: "shift-handover", label: "Shift handover" },
] as const;

type Kind = (typeof EMIT_TYPES)[number]["key"];

const shortId = () => crypto.randomUUID().slice(0, 8).toUpperCase();

const FIELD = "h-11 w-full rounded-lg border border-line bg-surface px-2.5 text-body lg:h-9";

export function EmitPanel({ siteId, userId, onEmitted }: { siteId: string; userId: string; onEmitted: () => void }) {
  const [kind, setKind] = useState<Kind>("work-order");
  const [assetId, setAssetId] = useState("EQ-101");
  const [failureCode, setFailureCode] = useState("MECH-SEAL-FAIL");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function emit() {
    setBusy(true);
    setMsg(null);
    const base = { source_system: "manual", site_id: siteId };
    const asset = assetId.trim().toUpperCase();
    try {
      let res: { status: string; event_id: string };
      if (kind === "work-order") {
        // Assigned to the person emitting it, so the brief lands in an inbox someone can open.
        res = await postWorkOrder({ ...base, work_order_id: `WO-MANUAL-${shortId()}`, asset_id: asset, failure_code: failureCode.trim().toUpperCase(), description: note || "Manual work order", assigned_technician_id: userId, priority: "high" });
      } else if (kind === "ptw") {
        const assets = asset.split(/[\s,]+/).filter(Boolean);
        res = await postPtw({ ...base, ptw_id: `PTW-MANUAL-${shortId()}`, work_area: note || "Manual isolation", asset_ids: assets, ptw_type: "isolation", issuing_engineer_id: userId });
      } else if (kind === "tag-out") {
        res = await postTagOut({ ...base, asset_id: asset, tag_out_reason: note || "Scheduled isolation", performed_by: userId });
      } else if (kind === "inspection-complete") {
        res = await postInspectionComplete({ ...base, asset_id: asset, inspection_type: "visual", result: "failed", findings: note || "Visual finding", performed_by: userId });
      } else if (kind === "alarm") {
        res = await postAlarm({ ...base, asset_id: asset, alarm_id: `ALM-${shortId()}`, alarm_tag: `${asset}-PAH`, alarm_description: note || "High pressure", severity: "high", acknowledged_by: userId });
      } else {
        // The handover brief goes to the incoming lead. This sent the literal ids "shift-A"/"shift-B",
        // which are not users, so the brief was addressed to no one.
        res = await postShiftHandover({ ...base, outgoing_shift_lead_id: "previous-shift", incoming_shift_lead_id: userId, handover_time: new Date().toISOString() });
      }
      setMsg(res.status === "deduplicated"
        ? "Duplicate suppressed — an identical event arrived within the 10-minute window."
        : kind === "ptw"
          ? "Permit emitted — its brief will reach your inbox and wait for a reliability countersignature."
          : "Event emitted — brief assembly triggered.");
      setNote("");
      onEmitted();
    } catch (err) {
      setMsg(err instanceof Error ? `Failed — ${err.message}` : "Failed — backend unreachable.");
    } finally {
      setBusy(false);
    }
  }

  const needsAsset = kind !== "shift-handover";

  return (
    <section className="mt-5 rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
      <div>
        <h2 className="text-sm font-semibold text-ink">Emit operational event</h2>
        <p className="mt-0.5 text-caption text-muted">
          Send an event through the live event-to-brief workflow. Briefs are addressed to you, so you can open them.
        </p>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[180px_160px_minmax(220px,1fr)_auto] lg:items-end">
        <label className="flex flex-col gap-1 text-caption">
          <span className="font-semibold text-ink">Type</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as Kind)} className={FIELD}>
            {EMIT_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </label>
        {needsAsset && (
          <label className="flex flex-col gap-1 text-caption">
            <span className="font-semibold text-ink">{kind === "ptw" ? "Boundary assets" : "Asset"}</span>
            <input value={assetId} onChange={(e) => setAssetId(e.target.value)}
              placeholder={kind === "ptw" ? "V-247, XV-203" : "EQ-101"} className={FIELD} />
          </label>
        )}
        {kind === "work-order" && (
          <label className="flex flex-col gap-1 text-caption">
            <span className="font-semibold text-ink">Failure code</span>
            <input value={failureCode} onChange={(e) => setFailureCode(e.target.value)} className={FIELD} />
          </label>
        )}
        <label className="flex min-w-0 flex-col gap-1 text-caption sm:col-span-2 lg:col-span-1">
          <span className="font-semibold text-ink">{kind === "ptw" ? "Work area" : "Note"}</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" className={FIELD} />
        </label>
        <Button className="h-11 sm:col-span-2 lg:col-span-1 lg:h-9" variant="primary" onClick={emit} disabled={busy || (needsAsset && !assetId.trim())}>
          {busy ? "Emitting…" : "Emit"}
        </Button>
      </div>
      {msg && <p role="status" className="mt-3 text-caption text-muted">{msg}</p>}
    </section>
  );
}
