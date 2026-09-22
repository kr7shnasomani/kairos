"use client";

// ⌘K command palette + keyboard-shortcut help sheet. Opened from AppShell
// (global key listener + sidebar search button). Plain substring filtering —
// the item list is small enough that fuzzy ranking would be over-engineering.
import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "./ui";
import { cn } from "@/lib/utils";

import { Icon } from "@/components/icon";
export interface PaletteItem {
  group: string;
  label: string;
  href?: string;
  action?: () => void;
  hint?: string;
}

const ASSET_ID = /^[a-z]{1,4}-\d+\w*$/i;

export function CommandPalette({
  open,
  onClose,
  items,
}: {
  open: boolean;
  onClose: () => void;
  items: PaletteItem[];
}) {
  // Mount-gated so query/selection state resets on every open without effects.
  if (!open) return null;
  return <PaletteDialog onClose={onClose} items={items} />;
}

function PaletteDialog({ onClose, items }: { onClose: () => void; items: PaletteItem[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();

  const q = query.trim().toLowerCase();
  const filtered = q ? items.filter((i) => i.label.toLowerCase().includes(q)) : items;
  // Typing something shaped like an asset tag offers a direct jump even when
  // the tag isn't in the nav list.
  const assetJump: PaletteItem[] = ASSET_ID.test(query.trim())
    ? [{ group: "Assets", label: `Open asset ${query.trim().toUpperCase()}`, href: `/assets/${query.trim().toUpperCase()}` }]
    : [];
  const results = [...assetJump, ...filtered];

  function run(item: PaletteItem) {
    onClose();
    if (item.href) router.push(item.href);
    item.action?.();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && results[active]) { e.preventDefault(); run(results[active]); }
  }

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex justify-center p-4 pt-[14vh]" role="dialog" aria-modal="true" aria-label="Command palette">
      <button type="button" className="absolute inset-0 animate-[overlay-in_150ms_ease-out] bg-[var(--scrim)]" aria-label="Close palette" onClick={onClose} />
      <div
        className="relative h-fit w-full max-w-lg animate-[panel-in_150ms_ease-out] overflow-hidden rounded-xl border border-line bg-surface shadow-xl"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <Icon name="magnifying-glass" size={15} className="shrink-0 text-muted" />
          <input
            autoFocus
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }}
            placeholder="Search pages, assets, actions…"
            aria-label="Search commands"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={results[active] ? `${listId}-${active}` : undefined}
            className="h-11 w-full bg-transparent text-body outline-none placeholder:text-muted"
          />
          <kbd className="shrink-0 rounded border border-line bg-surface-2 px-1.5 py-0.5 text-micro text-muted">esc</kbd>
        </div>

        <ul id={listId} role="listbox" aria-label="Commands" className="max-h-[50vh] overflow-y-auto p-2">
          {results.length === 0 && (
            <li className="px-3 py-6 text-center text-body text-muted">No matches for “{query.trim()}”.</li>
          )}
          {results.map((item, i) => {
            const header = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <li key={`${item.group}-${item.label}`}>
                {header && (
                  <p className="px-3 pb-1 pt-2 text-micro font-bold uppercase tracking-[0.1em] text-muted">{header}</p>
                )}
                <button
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onClick={() => run(item)}
                  onMouseMove={() => setActive(i)}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-body transition-colors",
                    i === active ? "bg-accent-soft text-accent" : "text-ink",
                  )}
                >
                  <span className="truncate">{item.label}</span>
                  {item.hint && <kbd className="shrink-0 rounded border border-line bg-surface-2 px-1.5 py-0.5 text-micro text-muted">{item.hint}</kbd>}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

const SHORTCUTS: { keys: string; label: string }[] = [
  { keys: "⌘K / Ctrl+K", label: "Command palette" },
  { keys: "?", label: "This shortcut sheet" },
  { keys: "g b", label: "Go to Briefs" },
  { keys: "g c", label: "Go to Copilot" },
  { keys: "g a", label: "Go to Assets" },
  { keys: "g e", label: "Go to Events" },
  { keys: "g g", label: "Go to Graph" },
  { keys: "g d", label: "Go to Documents" },
  { keys: "g q", label: "Go to Quarantine" },
  { keys: "g v", label: "Go to Governance" },
  { keys: "g m", label: "Go to Overview" },
  { keys: "esc", label: "Close dialogs" },
];

export function ShortcutsHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <Modal title="Keyboard shortcuts" onClose={onClose}>
      <ul className="space-y-1.5">
        {SHORTCUTS.map((s) => (
          <li key={s.keys} className="flex items-center justify-between gap-3 text-body">
            <span className="text-ink">{s.label}</span>
            <kbd className="rounded border border-line bg-surface-2 px-1.5 py-0.5 text-micro text-muted">{s.keys}</kbd>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
