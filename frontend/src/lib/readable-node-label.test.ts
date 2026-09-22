import { describe, expect, it } from "vitest";
import { readableNodeLabel } from "./api";

describe("readableNodeLabel", () => {
  it("turns a vault filename into a title", () => {
    expect(readableNodeLabel("regulatory_clause_excerpts.pdf")).toBe("Regulatory clause excerpts");
    expect(readableNodeLabel("oem_bulletin_fp_sb_2025_04.pdf")).toBe("OEM bulletin fp SB 2025 04");
  });
  it("leaves identifiers alone", () => {
    expect(readableNodeLabel("EQ-101")).toBe("EQ-101");
    expect(readableNodeLabel("Shell and Tube Heat Exchanger")).toBe("Shell and Tube Heat Exchanger");
  });
});
