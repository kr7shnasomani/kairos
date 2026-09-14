"use client";

// Register assets — one at a time, or the EAM golden record as a CSV (Layer 1).
// Separate from /assets/bootstrap on purpose: registering equipment is a data-entry job for admin and
// engineer, confirming a provisional identity is an admin review. They shared one page and both Assets
// buttons landed on it.
import Link from "next/link";
import { useEffect, useState } from "react";
import { bulkImportAssets, confirmAssetIdentity, type AssetBulkImportResult, type AssetImportRow } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { Button, PageHeader } from "@/components/ui";
import { PageSkeleton } from "@/components/skeleton";
import { MDM_ROLES } from "../identity-action";

type Criticality = AssetImportRow["criticality"];

const CRITICALITY: { value: Criticality; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "safety_critical", label: "Safety-critical" },
  { value: "non_critical", label: "Non-critical" },
];

const CSV_REQUIRED = ["tag_number", "name", "equipment_class", "criticality", "facility_id"] as const;
const CSV_TEMPLATE = "tag_number,name,equipment_class,criticality,facility_id,site_id,parent_asset_id";

const FIELD = "h-11 w-full rounded-lg border border-line bg-surface px-3 text-body text-ink outline-none focus:border-accent md:h-9";

/** "Safety critical", "safety-critical" and "SAFETY_CRITICAL" all mean the one enum value. */
function normalizeCriticality(raw: string): Criticality | null {
  const v = raw.trim().toLowerCase().replace(/[\s-]+/g, "_");
  return CRITICALITY.some((c) => c.value === v) ? (v as Criticality) : null;
}

/** Minimal CSV line split that honours double-quoted fields ("Pump, Line 2"). */
function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"' && quoted && line[i + 1] === '"') { cell += '"'; i++; }
    else if (ch === '"') quoted = !quoted;
    else if (ch === "," && !quoted) { cells.push(cell.trim()); cell = ""; }
    else cell += ch;
  }
  cells.push(cell.trim());
  return cells;
}

/** EAM export → import rows. Rows missing a required field or with an unknown criticality are
 *  reported, not silently dropped; the rest still import. `site_id` defaults to the importer's site. */
function parseAssetCsv(text: string, defaultSite: string): { rows: AssetImportRow[]; errors: string[] } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length === 0) return { rows: [], errors: ["The file is empty."] };
  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  const missing = CSV_REQUIRED.filter((h) => !header.includes(h));
  if (missing.length) return { rows: [], errors: [`Missing column(s): ${missing.join(", ")}.`] };

  const rows: AssetImportRow[] = [];
  const errors: string[] = [];
  lines.slice(1).forEach((line, i) => {
    const cells = splitCsvLine(line);
    const get = (key: string) => cells[header.indexOf(key)]?.trim() ?? "";
    const rowNo = i + 2;
    const empty = CSV_REQUIRED.filter((k) => !get(k));
    if (empty.length) { errors.push(`Row ${rowNo}: missing ${empty.join(", ")}.`); return; }
    const criticality = normalizeCriticality(get("criticality"));
    if (!criticality) { errors.push(`Row ${rowNo}: criticality "${get("criticality")}" is not critical, safety_critical or non_critical.`); return; }
    const tag = get("tag_number").toUpperCase();
    rows.push({
      asset_id: get("asset_id").toUpperCase() || tag,
      tag_number: tag,
      name: get("name"),
      equipment_class: get("equipment_class"),
      criticality,
      site_id: get("site_id") || defaultSite,
      facility_id: get("facility_id"),
      ...(get("parent_asset_id") ? { parent_asset_id: get("parent_asset_id").toUpperCase() } : {}),
      eam_source: get("eam_source") || "csv_import",
    });
  });
  return { rows, errors };
}

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

function RegisterAssetForm({ userId, siteId }: { userId: string; siteId: string }) {
  const [form, setForm] = useState({ tag_number: "", name: "", equipment_class: "", criticality: "critical" as Criticality, facility_id: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string; tag?: string } | null>(null);
  const update = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const tag = form.tag_number.trim().toUpperCase();
    setBusy(true);
    setMessage(null);
    try {
      await confirmAssetIdentity({
        asset_id: tag,
        tag_number: tag,
        name: form.name.trim(),
        equipment_class: form.equipment_class.trim(),
        criticality: form.criticality,
        site_id: siteId,
        facility_id: form.facility_id.trim().toUpperCase(),
        confirmed_by_user_id: userId,
      });
      setMessage({ ok: true, text: `${tag} registered with a confirmed identity.`, tag });
      setForm((f) => ({ ...f, tag_number: "", name: "" }));
    } catch {
      setMessage({ ok: false, text: `${tag} was not registered. Check the fields and try again.` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5">
      <label className="grid gap-1">
        <span className="text-label font-semibold text-muted">Tag number</span>
        <input required value={form.tag_number} onChange={update("tag_number")} placeholder="e.g. P-205" className={FIELD} />
      </label>
      <label className="grid gap-1">
        <span className="text-label font-semibold text-muted">Name</span>
        <input required value={form.name} onChange={update("name")} placeholder="e.g. Centrifugal Feed Pump" className={FIELD} />
      </label>
      <label className="grid gap-1">
        <span className="text-label font-semibold text-muted">Equipment class</span>
        <input required value={form.equipment_class} onChange={update("equipment_class")} placeholder="e.g. Rotating – Centrifugal Pump" className={FIELD} />
      </label>
      <label className="grid gap-1">
        <span className="text-label font-semibold text-muted">Criticality</span>
        <select value={form.criticality} onChange={update("criticality")} className={FIELD}>
          {CRITICALITY.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </label>
      <label className="grid gap-1">
        <span className="text-label font-semibold text-muted">Facility</span>
        <input required value={form.facility_id} onChange={update("facility_id")} placeholder="Facility code, e.g. RPC" className={FIELD} />
      </label>
      <div className="flex flex-col justify-end gap-1">
        <span className="text-label text-muted">Site · <span className="tabular font-semibold text-ink">{siteId || "—"}</span> (from your account)</span>
        <Button type="submit" variant="primary" className="h-11 md:h-9" disabled={busy || !siteId}>
          {busy ? "Registering…" : "Register asset"}
        </Button>
      </div>
      {message && (
        <p role="status" className={`text-caption sm:col-span-2 ${message.ok ? "text-verified" : "text-danger"}`}>
          {message.text}
          {message.tag && (
            <> <Link href={`/assets/${encodeURIComponent(message.tag)}`} className="font-semibold text-link hover:underline">Open {message.tag}</Link></>
          )}
        </p>
      )}
    </form>
  );
}

function BulkImportPanel({ siteId }: { siteId: string }) {
  const [parsed, setParsed] = useState<{ file: string; rows: AssetImportRow[]; errors: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AssetBulkImportResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function choose(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    setResult(null);
    setFailure(null);
    if (!file) { setParsed(null); return; }
    const { rows, errors } = parseAssetCsv(await readFile(file), siteId);
    setParsed({ file: file.name, rows, errors });
  }

  async function runImport() {
    if (!parsed?.rows.length) return;
    setBusy(true);
    setFailure(null);
    try {
      setResult(await bulkImportAssets(parsed.rows));
    } catch {
      setFailure("The import did not complete. Nothing is lost — fix the connection and import the file again.");
    } finally {
      setBusy(false);
    }
  }

  const skipped = result ? result.already_present.length + result.duplicate_in_payload.length : 0;
  const rejected = result ? result.site_forbidden.length + result.failed.length : 0;

  return (
    <div className="grid gap-3 p-4 sm:p-5">
      <p className="text-caption text-muted">
        Columns: <code className="tabular text-ink">{CSV_TEMPLATE}</code>. <code className="tabular">site_id</code> and{" "}
        <code className="tabular">parent_asset_id</code> are optional. Assets already registered are skipped, not overwritten.
      </p>
      <label className="grid gap-1">
        <span className="text-label font-semibold text-muted">EAM export (CSV)</span>
        <input type="file" accept=".csv,text/csv" onChange={choose} className="text-caption text-muted file:mr-3 file:rounded-md file:border file:border-line file:bg-surface-2 file:px-2.5 file:py-1 file:text-label file:font-semibold file:text-ink" />
      </label>
      {parsed && (
        <div className="grid gap-2">
          <p className="text-caption text-ink">
            <span className="font-semibold">{parsed.file}</span> · {parsed.rows.length} row(s) ready
            {parsed.errors.length > 0 && <span className="text-danger"> · {parsed.errors.length} row(s) need fixing</span>}
          </p>
          {parsed.errors.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-label text-danger">
              {parsed.errors.slice(0, 5).map((err) => <li key={err}>{err}</li>)}
            </ul>
          )}
          <div>
            <Button variant="primary" className="h-11 md:h-9" disabled={busy || parsed.rows.length === 0} onClick={runImport}>
              {busy ? "Importing…" : `Import ${parsed.rows.length} asset${parsed.rows.length === 1 ? "" : "s"}`}
            </Button>
          </div>
        </div>
      )}
      {failure && <p role="alert" className="text-caption text-danger">{failure}</p>}
      {result && (
        <p role="status" className="text-caption text-ink">
          <span className="font-semibold text-verified">{result.created} created</span>
          {skipped > 0 && <span className="text-muted"> · {skipped} already registered or duplicated</span>}
          {rejected > 0 && <span className="text-danger"> · {rejected} rejected (site or validation)</span>}
        </p>
      )}
    </div>
  );
}

export default function RegisterAssetPage() {
  const [ready, setReady] = useState(false);
  const [role, setRole] = useState<Role | null>(null);
  const [userId, setUserId] = useState("");
  const [siteId, setSiteId] = useState("");

  useEffect(() => {
    getMe().then((u) => {
      if (u) {
        setRole(u.role);
        setUserId(u.user_id);
        setSiteId(u.site_id);
      }
      setReady(true);
    });
  }, []);

  if (!ready) return <PageSkeleton />;
  const allowed = role !== null && MDM_ROLES.includes(role);

  return (
    <div data-testid="register-workspace" className="mx-auto max-w-5xl">
      <Link href="/assets" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Assets
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Layer 1 · Master data management"
        title="Register assets"
        lede="Add equipment to the canonical registry one at a time, or import the golden record from your EAM system."
      />

      {!allowed && (
        <div className="mt-6 rounded-xl border border-line bg-surface p-5 text-body text-muted">
          Registering assets requires the <span className="font-semibold text-ink">engineer</span> or{" "}
          <span className="font-semibold text-ink">admin</span> role.
        </div>
      )}

      {allowed && (
        <div className="mt-6 space-y-6">
          <section data-testid="register-asset" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
            <div className="border-b border-line px-4 py-4 sm:px-5">
              <h2 className="text-sm font-semibold text-ink">Register an asset</h2>
              <p className="mt-0.5 text-caption text-muted">One piece of equipment, confirmed by you as it is created.</p>
            </div>
            <RegisterAssetForm userId={userId} siteId={siteId} />
          </section>

          <section data-testid="import-assets" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
            <div className="border-b border-line px-4 py-4 sm:px-5">
              <h2 className="text-sm font-semibold text-ink">Import from an EAM export</h2>
              <p className="mt-0.5 text-caption text-muted">Bulk-register the golden record. Rows that cannot land are reported; the rest still import.</p>
            </div>
            <BulkImportPanel siteId={siteId} />
          </section>
        </div>
      )}
    </div>
  );
}
