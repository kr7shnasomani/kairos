"use client";

// What extraction wrote for this document: entities linked into the graph, plus the
// low-confidence ones held in quarantine instead.
import Link from "next/link";
import { Button, StatusBadge } from "@/components/ui";
import { getDocumentExtraction } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";

const TYPE_LABEL: Record<string, string> = {
  asset_tag: "Asset",
  person: "Person",
  organisation: "Organisation",
  topology_element: "Topology element",
};

export function ExtractionPanel({ documentId }: { documentId: string }) {
  const state = useFetch(() => getDocumentExtraction(documentId), [documentId]);

  return (
    <section data-testid="document-extraction">
      <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Extraction</h2>
      <div className="mt-2.5 rounded-xl border border-line bg-surface p-4">
        {state.status === "loading" && <div className="h-24 animate-pulse rounded-lg bg-surface-2" />}
        {state.status === "error" && (
          <div className="flex flex-wrap items-center justify-between gap-2 text-caption">
            <span className="text-muted">Couldn&apos;t load extraction results — {state.error.message}</span>
            <Button onClick={state.retry}>Retry</Button>
          </div>
        )}
        {state.status === "live" && (() => {
          const x = state.data;
          const pending = x.review_items.filter((r) => r.review_status === "pending").length;
          return (
            <>
              <div className="flex flex-wrap items-center gap-2 text-caption text-muted">
                <StatusBadge tone="info" dot={false}>{x.extraction_path === "ocr" ? "Read from image (OCR)" : "Native text"}</StatusBadge>
                <span className="tabular">{x.entities.length} entities · {x.graph_edges_created} graph edges</span>
              </div>
              {x.entities.length === 0 ? (
                <p className="mt-3 text-caption text-muted">No entities from this document are linked into the graph.</p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-caption">
                    <thead className="text-label uppercase tracking-[0.08em] text-muted">
                      <tr><th className="py-1.5 pr-3 font-semibold">Type</th><th className="py-1.5 pr-3 font-semibold">Value</th><th className="py-1.5 pr-3 text-right font-semibold">Confidence</th><th className="py-1.5 font-semibold">Status</th></tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {x.entities.map((e) => (
                        <tr key={`${e.entity_type}-${e.value}`}>
                          <td className="py-2 pr-3 text-muted">{TYPE_LABEL[e.entity_type] ?? e.entity_type.replace(/_/g, " ")}</td>
                          <td className="py-2 pr-3 font-medium text-ink">
                            {e.linked_asset_id ? <Link href={`/assets/${e.linked_asset_id}`} className="tabular text-accent hover:underline">{e.value}</Link> : e.value}
                          </td>
                          <td className="tabular py-2 pr-3 text-right">{Math.round(e.confidence * 100)}%</td>
                          <td className="py-2"><StatusBadge tone={e.requires_review ? "caution" : "verified"}>{e.requires_review ? "unverified" : "verified"}</StatusBadge></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {x.review_items.length > 0 && (
                <div className="mt-4 border-t border-line pt-3 text-caption">
                  <p className="font-semibold text-ink">Held in quarantine ({x.review_items.length}{pending ? `, ${pending} pending` : ""})</p>
                  <ul className="mt-1.5 space-y-1 text-muted">
                    {x.review_items.slice(0, 5).map((r) => <li key={r.item_id}>{r.content}</li>)}
                  </ul>
                  <Link href="/governance/quarantine" className="mt-2 inline-block font-semibold text-accent hover:underline">Review in quarantine →</Link>
                </div>
              )}
            </>
          );
        })()}
      </div>
    </section>
  );
}
