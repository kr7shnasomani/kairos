import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BrandLink } from "./brand-link";

describe("BrandLink", () => {
  afterEach(cleanup);

  it("links the Kairos logo and name to the public landing page", () => {
    render(<BrandLink />);

    expect(screen.getByRole("link", { name: /kairos home/i })).toHaveAttribute("href", "/");
    expect(screen.getByAltText("Kairos")).toHaveAttribute("src", "/logo.png");
  });

  it("accepts an in-app overview destination", () => {
    render(<BrandLink href="/overview" />);

    expect(screen.getByRole("link", { name: /kairos home/i })).toHaveAttribute("href", "/overview");
  });
});
