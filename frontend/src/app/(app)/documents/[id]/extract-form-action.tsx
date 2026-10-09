"use client";

// Send a form or checklist's fields to the review queue. Run only when a person asks: one checklist
// is about a dozen review items, and a queue that fills by itself gets approved without being read.
// The fields go to quarantine and nowhere else; promotion stays a human decision there.
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui";
import { RESOLVE_ROLES, useRole, visibleTo } from "@/components/use-role";
import { extractFormFields } from "@/lib/api";
import { plural } from "@/lib/labels";

export function ExtractFormAction({ documentId }: { documentId: string }) {
  const role = useRole();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (!visibleTo(RESOLVE_ROLES, role)) return null;

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await extractFormFields(documentId);
      if (result.status === "quarantined") setSent(result.fields);
      else setMessage("No form fields were found in this document.");
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      setMessage(text.endsWith("HTTP 409") ? "This document's form fields are already in the review queue." : "The fields could not be extracted. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section data-testid="extract-form">
      <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Form Fields</h2>
      <p className="mt-2 text-caption leading-relaxed text-muted">
        For a form or checklist, send each field and its value to the review queue. Nothing is added to the
        knowledge graph until a reviewer promotes it.
      </p>
      {sent === null ? (
        <div className="mt-3"><Button onClick={run} disabled={busy}>{busy ? "Extracting…" : "Extract form fields"}</Button></div>
      ) : (
        <p role="status" className="mt-3 text-caption font-semibold text-ink">
          {plural(sent, "field")} sent to the review queue.{" "}
          <Link href="/governance/quarantine" className="font-medium text-link hover:underline">Open the queue</Link>
        </p>
      )}
      {message && <p role="alert" className="mt-2 text-caption text-muted">{message}</p>}
    </section>
  );
}
