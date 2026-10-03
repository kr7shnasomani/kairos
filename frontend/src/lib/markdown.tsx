// Renders a Markdown document to React elements, never to an HTML string: the site's CSP forbids
// dangerouslySetInnerHTML, and building elements means a stray `<script>` in a doc is only text.
// `marked` does the parsing (tables, task lists, nesting); everything it hands back is walked here.
import Link from "next/link";
import path from "node:path";
import { Fragment, type ReactNode } from "react";
import { marked, type Token, type Tokens } from "marked";

export type Heading = { id: string; text: string; depth: number };
export type MarkdownContext = {
  /** The document being rendered, relative to docs/ and without ".md" (e.g. "implementation/status"). */
  file: string;
  /** Slugs of every published document, for link resolution. */
  slugs: ReadonlySet<string>;
  /** Diagram ids that have a pre-rendered /diagrams/<id>.svg. */
  diagrams: ReadonlySet<string>;
};

/** GitHub's heading anchor, so links written for the repo view (`#open-decisions`) keep working. */
export function slugify(text: string): string {
  return text.toLowerCase().trim().replace(/[^\p{L}\p{N}\s_-]/gu, "").replace(/\s/g, "-");
}

type Resolved = { kind: "external" | "anchor" | "doc" | "none"; href: string };

/** Where a link in a doc should go on the site. A link to repo source has no page here: kind "none". */
export function resolveHref(href: string, ctx: MarkdownContext): Resolved {
  if (/^(https?:|mailto:)/.test(href)) return { kind: "external", href };
  if (href.startsWith("#")) return { kind: "anchor", href };
  const [target, fragment] = href.split("#");
  if (!target.endsWith(".md")) return { kind: "none", href };
  // Relative to this document, or written from the repository root ("docs/API.md").
  const clean = (p: string) => p.replace(/^(\.\.\/)+/, "").replace(/^docs\//, "").replace(/\.md$/, "").toLowerCase();
  const slug = [path.posix.normalize(path.posix.join(path.posix.dirname(ctx.file), target)), target]
    .map(clean)
    .find((c) => ctx.slugs.has(c));
  if (!slug) return { kind: "none", href };
  return { kind: "doc", href: `/docs/${slug}${fragment ? `#${fragment}` : ""}` };
}

function textOf(tokens: Token[] | undefined, fallback = ""): string {
  if (!tokens) return fallback;
  return tokens.map((t) => ("tokens" in t && t.tokens ? textOf(t.tokens as Token[]) : "text" in t ? String(t.text) : "")).join("");
}

const LINK_CLASS = "text-(--lp-accent-text) underline decoration-(--lp-line) underline-offset-4 hover:decoration-current";

function inline(tokens: Token[] | undefined, ctx: MarkdownContext): ReactNode[] {
  return (tokens ?? []).map((t, i) => {
    switch (t.type) {
      case "text":
      case "escape":
        return <Fragment key={i}>{"tokens" in t && t.tokens ? inline(t.tokens, ctx) : (t as Tokens.Text).text}</Fragment>;
      case "strong":
        return <strong key={i} className="font-semibold text-(--lp-ink)">{inline((t as Tokens.Strong).tokens, ctx)}</strong>;
      case "em":
        return <em key={i}>{inline((t as Tokens.Em).tokens, ctx)}</em>;
      case "del":
        return <del key={i}>{inline((t as Tokens.Del).tokens, ctx)}</del>;
      case "codespan":
        return <code key={i} className="rounded bg-(--lp-band) px-1.5 py-0.5 font-mono text-[0.88em] text-(--lp-ink) [overflow-wrap:anywhere]">{(t as Tokens.Codespan).text}</code>;
      case "br":
        return <br key={i} />;
      case "link": {
        const l = t as Tokens.Link;
        const target = resolveHref(l.href, ctx);
        const children = inline(l.tokens, ctx);
        if (target.kind === "doc") return <Link key={i} href={target.href} className={LINK_CLASS}>{children}</Link>;
        if (target.kind === "anchor") return <a key={i} href={target.href} className={LINK_CLASS}>{children}</a>;
        if (target.kind === "external") return <a key={i} href={target.href} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>{children}</a>;
        return <Fragment key={i}>{children}</Fragment>; // a path in the repo: no page on this site
      }
      case "image": {
        const img = t as Tokens.Image;
        // eslint-disable-next-line @next/next/no-img-element
        return /^https?:/.test(img.href) ? <img key={i} src={img.href} alt={img.text} className="my-4 max-w-full border border-(--lp-line)" /> : null;
      }
      default:
        return null; // inline HTML: dropped, its text content (a separate token) stays
    }
  });
}

type State = { ctx: MarkdownContext; headings: Heading[]; seen: Map<string, number>; lastH2: string };

const HEADING_CLASS: Record<number, string> = {
  1: "mt-0 text-[40px] sm:text-[48px] text-(--lp-ink)",
  2: "mt-14 border-t border-(--lp-line) pt-8 text-[28px] text-(--lp-ink)",
  3: "mt-9 text-[20px] text-(--lp-ink)",
  4: "mt-7 text-[16px] font-semibold! tracking-normal! text-(--lp-ink)",
  5: "mt-6 text-[15px] font-semibold! tracking-normal! text-(--lp-ink)",
  6: "mt-6 text-[14px] font-semibold! tracking-normal! text-(--lp-ink)",
};

function blocks(tokens: Token[], s: State, tight = false): ReactNode[] {
  return tokens.map((t, i): ReactNode => {
    switch (t.type) {
      case "heading": {
        const h = t as Tokens.Heading;
        const text = textOf(h.tokens, h.text);
        const base = slugify(text);
        const n = s.seen.get(base) ?? 0;
        s.seen.set(base, n + 1);
        const id = n ? `${base}-${n}` : base;
        if (h.depth === 2) s.lastH2 = text;
        if (h.depth >= 2 && h.depth <= 3) s.headings.push({ id, text, depth: h.depth });
        const Tag = `h${h.depth}` as "h1";
        return (
          <Tag key={i} id={id} className={`scroll-mt-24 leading-[1.1]! ${HEADING_CLASS[h.depth]}`}>
            {inline(h.tokens, s.ctx)}
          </Tag>
        );
      }
      case "paragraph":
        return <p key={i} className="mt-4 text-[15px] leading-7 text-(--lp-muted)">{inline((t as Tokens.Paragraph).tokens, s.ctx)}</p>;
      case "text": // a list item's own text: no paragraph box around it
        return <Fragment key={i}>{inline((t as Tokens.Text).tokens ?? [t], s.ctx)}</Fragment>;
      case "code": {
        const c = t as Tokens.Code;
        const id = /^\W*(\w+)/.exec(s.lastH2)?.[1] ?? "";
        if (c.lang === "mermaid" && s.ctx.diagrams.has(id)) {
          return (
            <figure key={i} className="mt-6">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/diagrams/${id}.svg`} alt={s.lastH2} className="w-full border border-(--lp-line) bg-white p-3" />
              <details className="mt-2 text-[13px] text-(--lp-muted)">
                <summary className="cursor-pointer">Mermaid source</summary>
                <pre className="mt-2 overflow-x-auto border border-(--lp-line) bg-(--lp-band) p-4 font-mono text-[12.5px] leading-6 text-(--lp-ink)"><code>{c.text}</code></pre>
              </details>
            </figure>
          );
        }
        return (
          <pre key={i} className="mt-5 overflow-x-auto border border-(--lp-line) bg-(--lp-band) p-4 font-mono text-[12.5px] leading-6 text-(--lp-ink)">
            <code>{c.text}</code>
          </pre>
        );
      }
      case "blockquote":
        return (
          <blockquote key={i} className="mt-5 border border-(--lp-line) bg-(--lp-band) px-5 pb-4 pt-1 [&_p:first-child]:mt-3">
            {blocks((t as Tokens.Blockquote).tokens, s)}
          </blockquote>
        );
      case "hr":
        return <hr key={i} className="my-10 border-(--lp-line)" />;
      case "list": {
        const l = t as Tokens.List;
        const Tag = l.ordered ? "ol" : "ul";
        return (
          <Tag
            key={i}
            start={l.ordered && l.start !== "" && l.start !== 1 ? Number(l.start) : undefined}
            className={`${tight ? "mt-2" : "mt-4"} space-y-1.5 pl-6 text-[15px] leading-7 text-(--lp-muted) ${l.ordered ? "list-decimal" : "list-disc"} marker:text-(--lp-muted)`}
          >
            {l.items.map((item, j) => (
              <li key={j}>
                {item.task && <span aria-hidden="true" className="mr-1.5 font-mono text-[13px]">{item.checked ? "[x]" : "[ ]"}</span>}
                {blocks(item.tokens, s, true)}
              </li>
            ))}
          </Tag>
        );
      }
      case "table": {
        const tb = t as Tokens.Table;
        const align = (a: string | null) => (a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left");
        return (
          <div key={i} className="mt-5 overflow-x-auto">
            <table className="w-full border-collapse text-[13.5px] leading-6">
              <thead>
                <tr>
                  {tb.header.map((c, j) => (
                    <th key={j} className={`border border-(--lp-line) bg-(--lp-band) px-3 py-2 font-semibold text-(--lp-ink) ${align(c.align)}`}>{inline(c.tokens, s.ctx)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tb.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((c, j) => (
                      <td key={j} className={`border border-(--lp-line) px-3 py-2 align-top text-(--lp-muted) ${align(c.align)}`}>{inline(c.tokens, s.ctx)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      default:
        return null; // space, block HTML, link definitions
    }
  });
}

export function renderMarkdown(source: string, ctx: MarkdownContext): { content: ReactNode; headings: Heading[] } {
  const state: State = { ctx, headings: [], seen: new Map(), lastH2: "" };
  const content = blocks(marked.lexer(source), state);
  return { content, headings: state.headings };
}
