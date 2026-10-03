import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { getDoc, listDocs } from "@/lib/docs";
import { renderMarkdown } from "@/lib/markdown";

type Params = { slug: string[] };

// Only the published documents exist; anything else is a 404, not a build-time guess.
export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return listDocs().map((d) => ({ slug: d.slug.split("/") }));
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const doc = getDoc((await params).slug.join("/"));
  return doc ? { title: `${doc.meta.label} | Kairos documentation`, description: doc.meta.summary } : {};
}

/** Diagram ids with a pre-rendered SVG (tools/render_diagrams.sh writes them from docs/DIAGRAMS.md). */
function renderedDiagrams(): Set<string> {
  const dir = path.join(process.cwd(), "public", "diagrams");
  return new Set(existsSync(/* turbopackIgnore: true */ dir) ? readdirSync(/* turbopackIgnore: true */ dir).filter((f) => f.endsWith(".svg")).map((f) => f.slice(0, -4)) : []);
}

export default async function DocPage({ params }: { params: Promise<Params> }) {
  const doc = getDoc((await params).slug.join("/"));
  if (!doc) notFound();
  const { content, headings } = renderMarkdown(doc.source, {
    file: doc.meta.file,
    slugs: new Set(listDocs().map((d) => d.slug)),
    diagrams: renderedDiagrams(),
  });
  return (
    <div className="mx-auto max-w-5xl xl:grid xl:grid-cols-[minmax(0,1fr)_200px] xl:gap-12">
      <article className="min-w-0 max-w-3xl">{content}</article>
      {headings.length > 2 && (
        <nav aria-label="On this page" className="hidden xl:block">
          <div className="sticky top-20 max-h-[calc(100dvh-7rem)] overflow-y-auto">
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-(--lp-muted)">On this page</p>
            <ul className="mt-3 space-y-1.5">
              {headings.map((h) => (
                <li key={h.id} className={h.depth === 3 ? "pl-3" : undefined}>
                  <a href={`#${h.id}`} className="block text-[12.5px] leading-5 text-(--lp-muted) hover:text-(--lp-ink)">{h.text}</a>
                </li>
              ))}
            </ul>
          </div>
        </nav>
      )}
    </div>
  );
}
