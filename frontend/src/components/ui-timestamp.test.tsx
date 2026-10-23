import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Timestamp } from "./ui";

describe("Timestamp", () => {
  it("renders the exact UTC value as the primary text", () => {
    render(<Timestamp value="2026-08-18T09:12:41.487511+00:00" />);
    expect(screen.getByText("2026-08-18 09:12:41 UTC")).toBeInTheDocument();
  });

  it("renders relative time as a secondary hint", () => {
    const { container } = render(<Timestamp value={new Date(Date.now() - 3_600_000).toISOString()} />);
    expect(container.textContent).toMatch(/ago/i);
  });

  it("omits the hint when relative is false", () => {
    const { container } = render(<Timestamp value="2026-08-18T09:12:41Z" relative={false} />);
    expect(container.textContent).not.toMatch(/ago/i);
    expect(container.textContent).toContain("2026-08-18 09:12:41");
  });

  it("renders an em dash for an absent value", () => {
    const { container } = render(<Timestamp value={null} />);
    expect(container.textContent).toBe("—");
  });

  it("renders an em dash for an unparseable value", () => {
    const { container } = render(<Timestamp value="not-a-date" />);
    expect(container.textContent).toBe("—");
  });

  it("exposes the full ISO value on the element for copy/inspection", () => {
    // Distinct value: this suite has no auto-cleanup between tests, so a
    // repeated timestamp would match renders left over from earlier cases.
    const iso = "2026-07-04T22:01:09.123456+00:00";
    render(<Timestamp value={iso} />);
    expect(screen.getByTitle(iso)).toBeInTheDocument();
  });
});
