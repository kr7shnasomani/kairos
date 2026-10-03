import Link from "next/link";
import { groupedDocs } from "@/lib/docs";

export default function DocsIndexPage() {
  const groups = groupedDocs();
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-[44px] text-(--lp-ink) sm:text-[56px]">Documentation</h1>
      <p className="mt-5 max-w-3xl text-[17px] leading-7 text-(--lp-muted)">
        How Kairos is built, how to run and deploy it, and how it is tested. The architecture and the API reference are the places to start.
      </p>
      {groups.length === 0 && (
        <p className="mt-10 border border-(--lp-line) bg-(--lp-band) p-5 text-[15px] text-(--lp-muted)">
          The documentation is not bundled into this build. It is read from the repository&apos;s <code className="font-mono">docs</code> folder when the site is built.
        </p>
      )}
      {groups.map(({ group, docs }) => (
        <section key={group} className="mt-12">
          <h2 className="text-[24px] text-(--lp-ink)">{group}</h2>
          <ul className="mt-5 grid border-l border-t border-(--lp-line) sm:grid-cols-2">
            {docs.map((d) => (
              <li key={d.slug} className="border-b border-r border-(--lp-line) bg-white">
                <Link href={`/docs/${d.slug}`} className="block h-full p-5 transition-colors hover:bg-(--lp-band)">
                  <span className="block text-[16px] font-semibold text-(--lp-ink)">{d.label}</span>
                  <span className="mt-1.5 block text-[14px] leading-6 text-(--lp-muted)">{d.summary}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
