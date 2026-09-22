import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { KpiCard } from "./ui";

describe("KpiCard color hierarchy", () => {
  afterEach(cleanup);

  it("carries the tone in a square marker beside the label", () => {
    render(<KpiCard label="Assets tracked" value="12" tone="info" />);

    expect(screen.getByTestId("kpi-accent")).toHaveClass("size-1.5", "bg-info");
  });

  it("reserves an attention marker for warning states", () => {
    render(<KpiCard label="Open conflicts" value="3" tone="danger" />);

    expect(screen.getByTestId("kpi-accent")).toHaveClass("bg-danger");
  });
});
