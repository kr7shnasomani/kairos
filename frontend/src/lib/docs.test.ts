import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let dir: string;

beforeEach(() => {
  vi.resetModules();
  dir = mkdtempSync(path.join(tmpdir(), "kairos-docs-"));
  process.env.KAIROS_DOCS_DIR = dir;
  mkdirSync(path.join(dir, "implementation"));
  writeFileSync(path.join(dir, "API.md"), "# API\n\nSign in as admin@kairos.local with the key kairos-internal-dev-key.\n");
  writeFileSync(path.join(dir, "DEPLOY.md"), "# Deployment\n\nssh ubuntu@3.7.186.159\n");
  writeFileSync(path.join(dir, "implementation", "status.md"), "# Status\n");
  writeFileSync(path.join(dir, "zzz-new.md"), "# A new document\n");
  writeFileSync(path.join(dir, "notes.txt"), "not markdown");
});

afterEach(() => {
  delete process.env.KAIROS_DOCS_DIR;
});

describe("docs", () => {
  it("publishes only the listed documents: a new or operational file is private until it is added", async () => {
    const { listDocs } = await import("./docs");
    expect(listDocs().map((d) => d.slug)).toEqual(["api"]);
  });

  it("uses the written label, group and summary", async () => {
    const { listDocs } = await import("./docs");
    expect(listDocs()[0]).toMatchObject({ label: "API reference", group: "Reference", summary: "Every REST route: who may call it, what it takes and what it returns." });
  });

  it("returns a listed document's source with sensitive values redacted, and nothing for any other slug", async () => {
    const { getDoc } = await import("./docs");
    const source = getDoc("api")?.source ?? "";
    expect(source).toContain("admin@example.com");
    expect(source).toContain("<dev-internal-key>");
    expect(source).not.toMatch(/kairos\.local|kairos-internal-dev-key/);
    expect(getDoc("deploy")).toBeNull();
    expect(getDoc("implementation/status")).toBeNull();
  });

  it("redacts hostnames, addresses and cloud identifiers", async () => {
    const { redact } = await import("./docs");
    const text = redact("api kairos-deterium.duckdns.org web kairos-deterium.vercel.app 3.7.186.159 and 127.0.0.1 i-012800d81f549557b prj_4XwxHOCZDI4Ioir6XEj4pubr3zhC");
    expect(text).toBe("api <api-host> web <web-host> <ip> and 127.0.0.1 <instance-id> <vercel-id>");
  });

  it("degrades to an empty site when the folder is not there", async () => {
    process.env.KAIROS_DOCS_DIR = path.join(dir, "missing");
    const { listDocs, docsRoot } = await import("./docs");
    expect(docsRoot()).toBeNull();
    expect(listDocs()).toEqual([]);
  });
});

// The real documents. Skipped where the docs folder is not visible (a build from frontend/ alone).
describe("the published documents", () => {
  const forbidden: [string, RegExp][] = [
    ["a seeded login address", /@kairos\.local/],
    ["a live hostname", /duckdns\.org|vercel\.app/],
    ["a development default credential", /kairos-internal-dev-key|kairos_dev_password/],
    ["an IP address", /\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b/],
    ["an AWS or Vercel identifier", /\bi-[0-9a-f]{12,}\b|\b(?:prj|team)_[A-Za-z0-9]{12,}\b|\barn:aws|\bAKIA[0-9A-Z]{12,}/],
    ["a private key or key file", /BEGIN [A-Z ]*PRIVATE KEY|\.pem\b/],
    ["a Supabase project reference", /ernffgrvdcikwwhkhiix/],
    ["a key that looks real", /\b(?:sk-|nvapi-|ghp_|xox[bp]-)[A-Za-z0-9_-]{16,}/],
  ];

  it.skipIf(!existsSync(path.resolve(process.cwd(), "..", "docs")))(
    "carry nothing sensitive after redaction",
    async () => {
      delete process.env.KAIROS_DOCS_DIR;
      const { listDocs, getDoc } = await import("./docs");
      const docs = listDocs();
      expect(docs.length).toBeGreaterThan(5);
      for (const d of docs) {
        const source = getDoc(d.slug)!.source;
        for (const [what, pattern] of forbidden) expect(source, `${d.file}.md still has ${what}`).not.toMatch(pattern);
      }
    },
  );
});
