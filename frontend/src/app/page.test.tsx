import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// next/font/google is compiled away by the Next toolchain; under plain vitest
// it has no loader, so stand in with the shape the page consumes.
vi.mock("./landing-fonts", () => ({
  instrumentSans: { variable: "--font-instrument" },
  dmSans: { variable: "--font-dm" },
}));

import Home from "./page";

describe("Home", () => {
  afterEach(cleanup);

  it("shows the public Kairos landing page instead of redirecting visitors", () => {
    render(<Home />);

    expect(screen.getByRole("heading", { level: 1, name: /the plant already knows/i })).toBeInTheDocument();

    // Two ways in, not three: the header CTA and the footer CTA. The duplicate
    // "Sign in" was removed, and the hero's primary action is the demo instead.
    const workspaceLinks = screen.getAllByRole("link", { name: /open workspace/i });
    expect(workspaceLinks).toHaveLength(2);
    for (const link of workspaceLinks) expect(link).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();

    // The hero leads with the recording. It leaves the site, so it must say so
    // to assistive tech and must not hand the opener a live window reference.
    const demo = screen.getByRole("link", { name: /watch demo/i });
    expect(demo).toHaveAttribute("href", expect.stringContaining("http"));
    expect(demo).toHaveAttribute("target", "_blank");
    expect(demo).toHaveAttribute("rel", expect.stringContaining("noreferrer"));

    // …and the path into the page itself is still there, unchanged.
    expect(screen.getByRole("link", { name: /see how it works/i })).toHaveAttribute("href", "#how");
  });

  // Readers who did not already know the domain could not tell what Kairos was.
  // The problem and the worked scenario are the fix, so they are load-bearing:
  // if either is dropped the page goes back to answering a question nobody asked.
  it("states the problem and walks one scenario before it makes a product claim", () => {
    render(<Home />);

    const problem = document.getElementById("problem") as HTMLElement;
    expect(problem).toBeInTheDocument();
    // The stakes, plus at least one attributed figure behind them.
    expect(problem).toHaveTextContent(/it is a safety problem/i);
    expect(within(problem).getByText("35%")).toBeInTheDocument();
    expect(problem).toHaveTextContent(/mckinsey/i);

    const how = document.getElementById("how") as HTMLElement;
    expect(how).toBeInTheDocument();
    // Five numbered steps, ending on the refusal — the step people miss.
    expect(within(how).getAllByRole("listitem")).toHaveLength(5);
    expect(how).toHaveTextContent(/a work order is raised on pump p-101/i);
    expect(how).toHaveTextContent(/when the evidence is thin, it says so/i);

    // Both must precede the first capability claim in document order.
    const capabilities = document.getElementById("capabilities") as HTMLElement;
    expect(problem.compareDocumentPosition(how)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(how.compareDocumentPosition(capabilities)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  // The brief's five build targets are covered by the capability tabs, whose
  // eyebrows already speak the brief's own vocabulary. A separate coverage
  // section restated all of it, so it was removed — this guards the coverage
  // itself rather than the section that used to duplicate it.
  it("covers every build target the brief named, in the capabilities themselves", () => {
    render(<Home />);

    for (const tab of ["Ingestion", "Expert copilot", "Root cause", "Compliance", "Briefs"]) {
      expect(screen.getByRole("button", { name: tab })).toBeInTheDocument();
    }

    const panel = document.getElementById("capability-panel") as HTMLElement;

    fireEvent.click(screen.getByRole("button", { name: "Root cause" }));
    expect(panel).toHaveTextContent(/maintenance intelligence/i);

    // Computer vision and OCR are claimed here and nowhere else. They used to be
    // restated in the capability list below, which is the duplication that list
    // was trimmed to remove — so this is now the only guard on them.
    fireEvent.click(screen.getByRole("button", { name: "Ingestion" }));
    expect(panel).toHaveTextContent(/universal ingestion/i);
    expect(panel).toHaveTextContent(/vision model/i);
    expect(panel).toHaveTextContent(/OCR/);

    // The regulatory frameworks, stated where they apply. Only the two the demo
    // actually seeds are named as loaded (`backend/scripts/seed_regulations.py`);
    // the rest are named as options, which is what `GET /compliance/frameworks`
    // reports. "Factories Act" is deliberately absent: it appears in the dataset's
    // clause-excerpt document, never as a framework the product can be set to.
    fireEvent.click(screen.getByRole("button", { name: "Compliance" }));
    expect(panel).toHaveTextContent(/quality and regulatory/i);
    expect(panel).toHaveTextContent(/OISD-117/);
    expect(panel).toHaveTextContent(/ISO 45001/);
    expect(panel).toHaveTextContent(/PESO/);
    expect(panel).not.toHaveTextContent(/Factories Act/i);

    // The cross-cutting work that has no screen of its own is stated once, in the
    // capability list under the tabs. Each row is pinned to something real:
    // moc_items runs draft -> pending_approval -> approved; services/pii.py redacts
    // at export only; circuit_breaker.check halts the graph write on a z-score.
    const section = document.getElementById("capabilities") as HTMLElement;
    expect(section).toHaveTextContent(/management of change/i);
    expect(section).toHaveTextContent(/DPDP Act 2023/);
    expect(section).toHaveTextContent(/non-conformance register/i);
    expect(section).toHaveTextContent(/blast radius/i);

    // And it does not restate what a tab already says.
    expect(section).not.toHaveTextContent(/computer vision for p&ids/i);

    // And both sections that duplicated the tabs are gone. Nothing may link to
    // them either: a nav cell pointing at a removed anchor is a dead click.
    expect(document.getElementById("scope")).toBeNull();
    expect(document.getElementById("platform")).toBeNull();
    expect(document.querySelector('a[href="#platform"]')).toBeNull();
  });

  it("quotes the measured benchmark figures, including the answer-quality range", () => {
    render(<Home />);

    // benchmark/RESULTS.md is explicit that uncertainty must be quoted rather
    // than a single flattering number, and that grading is deterministic.
    // The chart shows a point estimate, so the interval must still be
    // disclosed in the caption rather than quietly dropped.
    expect(screen.getByText("89%")).toBeInTheDocument();
    expect(screen.getByText("41/46")).toBeInTheDocument();
    // Two: the retrieval and provenance chart bars. KG linkage is quoted
    // document-centric (85%), not as a third 100% — see status.md on why the
    // asset-centric cut isn't trustworthy to publish as-is.
    expect(screen.getAllByText("100%")).toHaveLength(2);
    expect(screen.getByText("18 / 21")).toBeInTheDocument();
    expect(screen.getByText("6 / 6")).toBeInTheDocument();
    // Scoped to the <p>: a bare regex also matches every ancestor's textContent.
    expect(screen.getByText(/forty-six questions written by domain experts/i, { selector: "p" })).toBeInTheDocument();
    // Said once on the chart's own sub-label, and explained once in the filled cell
    // at the foot of the section. It used to be in the section intro as well, which
    // made that cell a repeat rather than the explanation.
    expect(screen.getAllByText(/graded by fixed rules/i, { selector: "p" })).toHaveLength(1);
    expect(screen.getByText(/fixed rules, never another model/i)).toBeInTheDocument();
    // The spread is carried by the chart itself, not rounded away in prose.
    expect(screen.getByText("41/46")).toBeInTheDocument();
    expect(screen.getByText(/95% confidence: 77 to 95/i)).toBeInTheDocument();
    // What the chart cannot show: which model answered, and why the misses understate it.
    expect(screen.getByText(/none from a fallback\s+model/i, { selector: "p" })).toBeInTheDocument();
    // The other harnesses are on the page too, with their real figures.
    expect(screen.getByText("13 / 13")).toBeInTheDocument();
    expect(screen.getByText("0 unsafe")).toBeInTheDocument();
    expect(screen.getByText("F1 0.912")).toBeInTheDocument();
    expect(screen.getByText("F1 0.805")).toBeInTheDocument();
    expect(screen.getByText("−9.5%")).toBeInTheDocument();
    expect(screen.getByText("0% errors")).toBeInTheDocument();
    expect(screen.getByText("No leak signal")).toBeInTheDocument();

    // No invented operational metrics.
    expect(screen.queryByText("98.4%")).not.toBeInTheDocument();
    expect(screen.queryByText("99.9%")).not.toBeInTheDocument();
  });

  it("names all six knowledge-edge properties that make an answer checkable", () => {
    render(<Home />);

    // Scoped to <code>: "confidence" also appears as a gate label in the
    // architecture diagram, and this test is about the property list.
    for (const property of ["valid_from", "valid_to", "authority_level", "document_id", "confidence", "verification_status"]) {
      expect(screen.getByText(property, { selector: "code" })).toBeInTheDocument();
    }
  });

  it("swaps the capability panel when another capability is selected", () => {
    render(<Home />);

    const panel = document.getElementById("capability-panel") as HTMLElement;
    expect(within(panel).getByRole("heading", { name: /told before you ask, but never spammed/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Field capture" }));

    expect(within(panel).getByRole("heading", { name: /capture that survives a dead zone/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Field capture" })).toHaveAttribute("aria-pressed", "true");
  });

  it("swaps the audience panel when another audience is selected", () => {
    render(<Home />);

    const panel = document.getElementById("audience-panel") as HTMLElement;
    expect(panel).toHaveTextContent(/the plant on one screen/i);

    fireEvent.click(screen.getByRole("button", { name: "Compliance officers" }));

    expect(panel).toHaveTextContent(/coverage you can export/i);
  });

  it("renders the FAQ as native disclosure elements so it works without JS", () => {
    const { container } = render(<Home />);

    // One category's questions at a time; the first answer starts open.
    const disclosures = container.querySelectorAll("details");
    expect(disclosures).toHaveLength(3);
    expect(disclosures[0].querySelector("summary")).toHaveTextContent(/what does kairos actually do/i);
    expect(disclosures[0]).toHaveAttribute("open");
  });

  it("switches the FAQ answers when another category is chosen", () => {
    render(<Home />);

    const answers = document.getElementById("faq-answers") as HTMLElement;
    expect(answers).toHaveTextContent(/what does kairos actually do/i);

    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));

    expect(answers).toHaveTextContent(/how was it evaluated/i);
    expect(answers).not.toHaveTextContent(/what does kairos actually do/i);
  });

  it("keeps every footer link pointed at a real destination", () => {
    const { container } = render(<Home />);

    const hrefs = [...container.querySelectorAll("footer a")].map((a) => a.getAttribute("href"));
    expect(hrefs.length).toBeGreaterThan(0);
    const allowedExternal = [
      "https://github.com/kr7shnasomani/kairos",
      "https://drive.google.com/file/d/18ZO95MckNtESg-Z2ruRBNnKq6JyB57rP/view?usp=drive_link",
    ];
    for (const href of hrefs) {
      const ok = href === "/login" || href === "/" || href?.startsWith("#") || allowedExternal.includes(href ?? "");
      expect(ok, `unexpected footer href: ${href}`).toBe(true);
    }
    // Every external link opens safely.
    for (const a of container.querySelectorAll('footer a[target="_blank"]')) {
      expect(a.getAttribute("rel")).toMatch(/noreferrer/);
    }
  });
});
