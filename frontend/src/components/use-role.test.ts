import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({ getMe: vi.fn() }));

import { READ_ONLY_ROLES, roleHome, routeAllowed } from "./use-role";

describe("demo role", () => {
  it("is read-only and lands on the Copilot", () => {
    expect(READ_ONLY_ROLES).toContain("demo");
    expect(roleHome("demo")).toBe("/copilot");
  });

  it.each(["/copilot", "/briefs", "/briefs/B-1", "/assets", "/assets/EQ-101", "/documents", "/documents/D-1", "/compliance", "/compliance/audit-pack", "/graph", "/settings"])(
    "may open %s",
    (path) => expect(routeAllowed(path, "demo")).toBe(true),
  );

  it.each([
    "/audit",
    "/offboarding",
    "/offboarding/S-1",
    "/governance",
    "/governance/quarantine",
    "/governance/model-gate",
    "/documents/ingest",
    "/assets/register",
    "/assets/bootstrap",
    "/events",
    "/field/voice",
    "/management",
    "/management/plant-state",
    "/rca",
    "/projects",
    "/system-health",
    "/unlisted-new-page",
  ])("may not open %s (deny by default)", (path) => expect(routeAllowed(path, "demo")).toBe(false));

  it("does not change what the other roles can open", () => {
    expect(routeAllowed("/copilot", "field_worker")).toBe(true);
    expect(routeAllowed("/audit", "compliance")).toBe(true);
    expect(routeAllowed("/governance", "engineer")).toBe(true);
  });
});
