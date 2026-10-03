import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderMarkdown, resolveHref, slugify, type MarkdownContext } from "./markdown";

const ctx: MarkdownContext = {
  file: "implementation/status",
  slugs: new Set(["api", "frontend", "implementation/status"]),
  diagrams: new Set(["overview"]),
};

function html(source: string, c: MarkdownContext = ctx) {
  const { content, headings } = renderMarkdown(source, c);
  return { ...render(<div>{content}</div>), headings };
}

describe("slugify", () => {
  it("matches GitHub's anchors so links written for the repo view still work", () => {
    expect(slugify("Open decisions, blocked on a human call")).toBe("open-decisions-blocked-on-a-human-call");
    expect(slugify("`GET /assets/{id}` (v2)")).toBe("get-assetsid-v2");
  });
});

describe("resolveHref", () => {
  it("sends a link to another document to its page on the site", () => {
    expect(resolveHref("../API.md#assets", ctx)).toEqual({ kind: "doc", href: "/docs/api#assets" });
    expect(resolveHref("docs/FRONTEND.md", ctx)).toEqual({ kind: "doc", href: "/docs/frontend" });
    expect(resolveHref("../../docs/API.md", ctx)).toEqual({ kind: "doc", href: "/docs/api" });
  });

  it("gives a path in the repository no link, because the site has no page for it", () => {
    expect(resolveHref("../backend/api/main.py", ctx).kind).toBe("none");
    expect(resolveHref("../README.md", ctx).kind).toBe("none");
  });

  it("keeps external links and in-page anchors", () => {
    expect(resolveHref("https://example.com/x", ctx).kind).toBe("external");
    expect(resolveHref("#section", ctx)).toEqual({ kind: "anchor", href: "#section" });
  });
});

describe("renderMarkdown", () => {
  it("gives headings anchors, de-duplicates repeats and lists h2 and h3 for the contents", () => {
    const { container, headings } = html("# Title\n\n## Setup\n\n### Run\n\n## Setup\n");
    expect([...container.querySelectorAll("h2")].map((h) => h.id)).toEqual(["setup", "setup-1"]);
    expect(headings).toEqual([
      { id: "setup", text: "Setup", depth: 2 },
      { id: "run", text: "Run", depth: 3 },
      { id: "setup-1", text: "Setup", depth: 2 },
    ]);
  });

  it("renders a table with its alignment, and nested lists", () => {
    const { container } = html("| a | b |\n|:--|--:|\n| 1 | 2 |\n\n- one\n  - nested\n- two\n");
    expect(container.querySelectorAll("th")[1]).toHaveClass("text-right");
    expect(container.querySelectorAll("td")).toHaveLength(2);
    expect(container.querySelector("ul ul li")).toHaveTextContent("nested");
  });

  it("links documents internally, opens external links in a new tab and unlinks repo paths", () => {
    const { container } = html("[api](../API.md#x) [ext](https://example.com) [src](../backend/main.py)");
    const links = [...container.querySelectorAll("a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/docs/api#x", "https://example.com"]);
    expect(links[1]).toHaveAttribute("rel", "noopener noreferrer");
    expect(container).toHaveTextContent("src");
  });

  it("shows a pre-rendered diagram for a mermaid block under its heading, else the code", () => {
    const source = "## `overview` and more\n\n```mermaid\ngraph TD\n```\n\n## `other`\n\n```mermaid\ngraph TD\n```\n";
    const { container } = html(source);
    expect(container.querySelector("img")).toHaveAttribute("src", "/diagrams/overview.svg");
    expect(container.querySelectorAll("pre")).toHaveLength(2); // the diagram's source, and the block with no SVG
  });

  it("never turns document text into markup", () => {
    const { container } = html("Text <script>alert(1)</script> and <b>bold</b>\n\n<div onclick=\"x()\">raw</div>\n");
    expect(container.querySelector("script, b, div[onclick]")).toBeNull();
  });
});
