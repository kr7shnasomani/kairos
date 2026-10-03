"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";

export type NavGroup = { group: string; docs: { slug: string; label: string }[] };

export function DocsNav({ groups }: { groups: NavGroup[] }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <nav aria-label="Documentation" className="px-4 py-4 lg:px-5 lg:py-6">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="docs-nav-list"
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 w-full items-center justify-between text-[14px] font-medium text-(--lp-ink) lg:hidden"
      >
        Browse the documentation
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <div id="docs-nav-list" className={cn("mt-3 space-y-6 lg:mt-0 lg:block", open ? "block" : "hidden")}>
        <Link
          href="/docs"
          onClick={() => setOpen(false)}
          className={cn("block text-[13px] hover:text-(--lp-ink)", pathname === "/docs" ? "font-semibold text-(--lp-ink)" : "text-(--lp-muted)")}
        >
          All documentation
        </Link>
        {groups.map(({ group, docs }) => (
          <section key={group}>
            <h2 className="text-[11px]! font-semibold uppercase tracking-[0.1em]! text-(--lp-muted)">{group}</h2>
            <ul className="mt-2 space-y-0.5">
              {docs.map((d) => {
                const href = `/docs/${d.slug}`;
                const active = pathname === href;
                return (
                  <li key={d.slug}>
                    <Link
                      href={href}
                      onClick={() => setOpen(false)}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "block border px-2.5 py-1.5 text-[13.5px] transition-colors",
                        active ? "border-(--lp-line) bg-(--lp-band) font-medium text-(--lp-ink)" : "border-transparent text-(--lp-muted) hover:text-(--lp-ink)",
                      )}
                    >
                      {d.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </nav>
  );
}
