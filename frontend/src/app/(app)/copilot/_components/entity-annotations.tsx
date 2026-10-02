"use client";

import { useState } from "react";
import type { ExtractedEntity } from "@/lib/copilot";
import { createAnnotation } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DemoGate } from "@/components/demo-gate";

const ENTITY_TYPES = [
  "Asset", "Equipment", "Part", "Substance", "Parameter",
  "FailureMode", "Valve", "Instrument", "Person", "Organization",
  "Location", "Event", "Document", "Procedure",
];

/** Inline entity annotation chips. Low-confidence entities get confirm / correct / delete.
 *  The demo account sees the chips but the controls are disabled: corrections write to the corpus. */
export function EntityAnnotations({ entities }: { entities: ExtractedEntity[] }) {
  const [actions, setActions] = useState<Record<string, "confirmed" | "deleted" | "corrected">>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [correctedTypes, setCorrectedTypes] = useState<Record<string, string>>({});

  function entityKey(e: ExtractedEntity) {
    return `${e.document_id}::${e.entity_text}`;
  }

  function annotate(e: ExtractedEntity, isCorrect: boolean, correctedType?: string) {
    const k = entityKey(e);
    // optimistic update
    setActions((a) => ({
      ...a,
      [k]: isCorrect ? "confirmed" : correctedType ? "corrected" : "deleted",
    }));
    setEditing(null);
    createAnnotation({
      document_id: e.document_id,
      entity_text: e.entity_text,
      entity_type: e.entity_type,
      corrected_type: correctedType,
      is_correct: isCorrect,
    }).catch(() => {}); // fire-and-forget; optimistic stays
  }

  const visible = entities.filter((e) => actions[entityKey(e)] !== "deleted");
  if (visible.length === 0) return null;

  return (
    <DemoGate>
    <div>
      <p className="mb-2 text-micro font-bold uppercase tracking-[0.1em] text-muted">
        Extracted entities
      </p>
      <div className="flex flex-wrap gap-2">
        {visible.map((e) => {
          const k = entityKey(e);
          const action = actions[k];
          const lowConf = e.confidence < 0.7;
          const isEditing = editing === k;

          return (
            <div key={k} className="flex flex-col gap-1">
              <div
                className={cn(
                  "flex items-center gap-1 border px-2.5 py-1 text-label",
                  action === "confirmed"
                    ? "border-[color-mix(in_srgb,var(--verified)_40%,var(--line))] bg-[color-mix(in_srgb,var(--verified)_8%,transparent)]"
                    : action === "corrected"
                    ? "border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] bg-accent-soft"
                    : lowConf
                    ? "border-[color-mix(in_srgb,var(--caution)_40%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_6%,transparent)]"
                    : "border-line bg-surface-2"
                )}
              >
                {lowConf && !action && (
                  <span
                    className="mr-0.5 size-1.5 shrink-0 rounded-full bg-caution"
                    aria-hidden="true"
                  />
                )}
                <span
                  className={cn(
                    "font-medium",
                    action === "confirmed"
                      ? "text-verified"
                      : action === "corrected"
                      ? "text-accent"
                      : "text-ink"
                  )}
                >
                  {e.entity_text}
                </span>
                <span className="ml-0.5 text-micro text-muted">
                  {action === "corrected" ? correctedTypes[k] : e.entity_type}
                </span>

                {lowConf && !action && !isEditing && (
                  <span className="ml-1 flex items-center gap-0.5">
                    <button
                      onClick={() => annotate(e, true)}
                      aria-label={`Confirm ${e.entity_text} as ${e.entity_type}`}
                      className="grid size-6 shrink-0 place-items-center text-label text-muted transition-colors hover:bg-[color-mix(in_srgb,var(--verified)_15%,transparent)] hover:text-verified"
                    >
                      ✓
                    </button>
                    <button
                      onClick={() => {
                        setCorrectedTypes((c) => ({ ...c, [k]: e.entity_type }));
                        setEditing(k);
                      }}
                      aria-label={`Correct type for ${e.entity_text}`}
                      className="grid size-6 shrink-0 place-items-center text-label text-muted transition-colors hover:bg-accent-soft hover:text-accent"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => annotate(e, false)}
                      aria-label={`Remove entity ${e.entity_text}`}
                      className="grid size-6 shrink-0 place-items-center text-label text-muted transition-colors hover:bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] hover:text-danger"
                    >
                      ✕
                    </button>
                  </span>
                )}

                {action === "confirmed" && (
                  <span className="ml-0.5 text-micro text-verified" aria-label="Confirmed">✓</span>
                )}
              </div>

              {isEditing && (
                <div className="ml-1 flex items-center gap-1.5 pl-1">
                  <select
                    value={correctedTypes[k]}
                    onChange={(ev) =>
                      setCorrectedTypes((c) => ({ ...c, [k]: ev.target.value }))
                    }
                    className="rounded border border-line bg-surface-2 px-1.5 py-0.5 text-label outline-none focus-visible:border-accent"
                    aria-label={`Select corrected type for ${e.entity_text}`}
                  >
                    {ENTITY_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => annotate(e, false, correctedTypes[k])}
                    className="rounded border border-accent bg-accent-soft px-2 py-0.5 text-label font-medium text-accent transition-colors hover:bg-[color-mix(in_srgb,var(--accent)_15%,transparent)]"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditing(null)}
                    className="rounded border border-line px-2 py-0.5 text-label text-muted transition-colors hover:text-ink"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
    </DemoGate>
  );
}
