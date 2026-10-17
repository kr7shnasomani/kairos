import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MetricCard } from "./ui";
import { Card, CardDescription, CardHeader, CardTitle } from "./ui-card";

describe("MetricCard (KpiCard alias)", () => {
  afterEach(cleanup);

  it("loading skeleton and loaded card share the fixed min-height (zero layout shift)", () => {
    const loading = render(<MetricCard label="Assets" value={12} loading />);
    expect(loading.container.firstElementChild).toHaveClass("min-h-[96px]");
    expect(screen.queryByText("Assets")).toBeNull();
    cleanup();

    const loaded = render(<MetricCard label="Assets" value={12} />);
    expect(loaded.container.firstElementChild).toHaveClass("min-h-[96px]");
    expect(screen.getByText("Assets")).toBeInTheDocument();
  });

  it("renders an em dash for null values", () => {
    render(<MetricCard label="Gaps" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("href renders the tile as a link", () => {
    render(<MetricCard label="Briefs" value={3} href="/briefs" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/briefs");
  });
});

describe("foundations mount check", () => {
  afterEach(cleanup);

  it("Card family composes", () => {
    render(
      <Card interactive>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Sub</CardDescription>
        </CardHeader>
        <p>Body</p>
      </Card>,
    );
    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });
});
