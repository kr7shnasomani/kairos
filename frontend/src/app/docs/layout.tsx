import type { Metadata } from "next";
import Link from "next/link";
import { groupedDocs } from "@/lib/docs";
import { DocsNav } from "./_components/docs-nav";

export const metadata: Metadata = {
  title: "Kairos documentation",
  description: "Architecture, API reference, deployment, tests and benchmarks for Kairos.",
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const groups = groupedDocs().map(({ group, docs }) => ({ group, docs: docs.map((d) => ({ slug: d.slug, label: d.label })) }));
  return (
    <div className="landing min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-(--lp-line) bg-(--lp-band)">
        <nav className="lp-frame flex h-[49px] items-stretch">
          <Link href="/" aria-label="Kairos home" className="flex items-center gap-2.5 border-r border-(--lp-line) px-4 sm:px-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="" width={24} height={24} className="object-cover" />
            <span className="lp-display text-[18px] text-(--lp-ink)">Kairos</span>
          </Link>
          <Link href="/docs" className="flex items-center border-r border-(--lp-line) px-4 text-[13px] font-medium text-(--lp-ink) sm:px-5">
            Documentation
          </Link>
          <div className="ml-auto flex items-stretch">
            <Link
              href="/login"
              className="flex items-center gap-2 border-l border-(--lp-line) bg-(--lp-accent-strong) px-5 text-[14px] font-medium text-white transition-transform duration-150 ease-out active:scale-[0.98] sm:px-7"
            >
              Open workspace <span aria-hidden="true">›</span>
            </Link>
          </div>
        </nav>
      </header>
      <div className="lp-frame lg:grid lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="border-b border-(--lp-line) lg:sticky lg:top-[49px] lg:h-[calc(100dvh-49px)] lg:self-start lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <DocsNav groups={groups} />
        </aside>
        <main id="main" className="min-w-0 px-5 py-10 sm:px-10 lg:py-14">{children}</main>
      </div>
    </div>
  );
}
