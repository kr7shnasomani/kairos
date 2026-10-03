// The public documentation: a short, explicit list of the files under the repo's docs/ folder, read at
// build time. docs/ stays the single source of truth (the repo links into it) and nothing is copied.
//
// This is an allowlist on purpose. A file that is not named here is not on the site, so a new document
// (a runbook, a status log, a review) is private until someone decides to publish it. Deployment,
// infrastructure, Docker, the status log, the code review and the presentation script are not published.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

export type DocMeta = { slug: string; file: string; label: string; group: string; summary: string };

const NAV: [group: string, entries: [file: string, label: string, summary: string][]][] = [
  ["Start here", [
    ["ARCHITECTURE", "Architecture", "The thirteen layers of Kairos, what each one does and how knowledge moves from a source document to a cited answer."],
    ["DIAGRAMS", "System diagrams", "The system design diagrams: the whole platform, then one drill-down each for the client, core, orchestration, services, data stores and model plane."],
    ["DATASET", "Datasets", "The golden dataset the benchmarks are measured against, and the second, larger showcase plant that fills a demo login."],
  ]],
  ["Reference", [
    ["API", "API reference", "Every REST route: who may call it, what it takes and what it returns."],
    ["BACKEND", "Backend", "The FastAPI services, workers and workflows, and every configuration setting."],
    ["FRONTEND", "Frontend", "The Next.js app: routes, design tokens, components and how each page reads the API."],
    ["DATABASE", "Databases", "Schemas for Supabase, Neo4j, Qdrant and Elasticsearch, and the rules each store enforces."],
    ["FIXTURES", "Fixtures", "The few places the backend serves fixture data on purpose, and how the interface discloses them."],
  ]],
  ["Quality", [
    ["TESTS", "Tests", "The test tiers, what each covers and how to run them."],
    ["BENCHMARKS", "Benchmarks", "How answer quality, retrieval and safety are measured, and how to read the results."],
  ]],
];

/**
 * Values that must never reach the site even though the source documents (written for the team) name
 * them: the seeded login addresses, the live hostnames, the development defaults and cloud identifiers.
 * Applied to every document before it is parsed. `docs.test.ts` fails if a published document still
 * carries anything that looks like one of these, so a new leak is caught rather than shipped.
 */
export const REDACTIONS: [RegExp, string][] = [
  [/\b([A-Za-z0-9_.-]+)@kairos\.local\b/g, "$1@example.com"],
  [/\b[a-z0-9-]+\.duckdns\.org\b/g, "<api-host>"],
  [/\b[a-z0-9-]+\.vercel\.app\b/g, "<web-host>"],
  [/\bkairos-internal-dev-key\b/g, "<dev-internal-key>"],
  [/\bkairos_dev_password\b/g, "<dev-neo4j-password>"],
  [/\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b/g, "<ip>"],
  [/\bi-[0-9a-f]{12,17}\b/g, "<instance-id>"],
  [/\b(?:prj|team)_[A-Za-z0-9]{20,}\b/g, "<vercel-id>"],
  [/\bernffgrvdcikwwhkhiix\b/g, "<project-ref>"],
];

export function redact(source: string): string {
  return REDACTIONS.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), source);
}

/** The docs folder, or null when this build cannot see it (the Docker image builds from frontend/ alone). */
export function docsRoot(): string | null {
  const dir = process.env.KAIROS_DOCS_DIR ?? path.resolve(process.cwd(), "..", "docs");
  return existsSync(/* turbopackIgnore: true */ dir) ? dir : null;
}

let cache: { root: string; docs: DocMeta[] } | null = null;

export function listDocs(): DocMeta[] {
  const root = docsRoot();
  if (!root) return [];
  if (cache?.root === root) return cache.docs;
  const docs = NAV.flatMap(([group, entries]) =>
    entries
      .filter(([file]) => existsSync(/* turbopackIgnore: true */ path.join(root, `${file}.md`)))
      .map(([file, label, summary]): DocMeta => ({ slug: file.toLowerCase(), file, label, group, summary })),
  );
  cache = { root, docs };
  return docs;
}

export function getDoc(slug: string): { meta: DocMeta; source: string } | null {
  const root = docsRoot();
  const meta = listDocs().find((d) => d.slug === slug);
  if (!root || !meta) return null;
  return { meta, source: redact(readFileSync(/* turbopackIgnore: true */ path.join(root, `${meta.file}.md`), "utf8")) };
}

/** The sidebar order: the groups of NAV, in order. */
export function groupedDocs(): { group: string; docs: DocMeta[] }[] {
  const docs = listDocs();
  return NAV.map(([group]) => ({ group, docs: docs.filter((d) => d.group === group) })).filter((g) => g.docs.length);
}
