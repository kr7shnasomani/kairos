import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetricCard } from "./ui";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui-card";
import { ErrorBoundary } from "./error-boundary";

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
        <CardContent>Body</CardContent>
      </Card>,
    );
    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });

  it("ErrorBoundary catches a render throw and shows the retry fallback", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    function Bomb(): React.ReactElement {
      throw new Error("kaboom");
    }
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    spy.mockRestore();
  });
});
