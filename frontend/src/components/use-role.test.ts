import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({ getMe: vi.fn() }));

import { ADMIN_VIEW_ROLES, PROMOTE_ROLES, roleHome, routeAllowed, visibleTo } from "./use-role";

describe("demo role", () => {
  it("is the demo identity and lands on the overview", () => {
    expect(roleHome("demo")).toBe("/overview");
  });

  it.each([
    "/copilot", "/briefs", "/assets", "/assets/register", "/assets/bootstrap", "/documents", "/documents/ingest",
    "/compliance", "/graph", "/settings", "/audit", "/offboarding", "/offboarding/S-1", "/governance",
    "/governance/model-gate", "/events", "/rca", "/projects", "/overview", "/overview/plant-state",
    "/overview/coverage", "/system-health", "/field/voice", "/field/deviation",
  ])("sees %s, like an admin", (path) => {
    expect(routeAllowed(path, "demo")).toBe(true);
    expect(routeAllowed(path, "admin")).toBe(true);
  });

  it("sees every control an admin sees, but that is visibility, not permission", () => {
    expect(visibleTo(PROMOTE_ROLES, "demo")).toBe(true);
    expect(visibleTo(PROMOTE_ROLES, "engineer")).toBe(false);
    expect(ADMIN_VIEW_ROLES).toEqual(["admin", "demo"]);
  });

  it("does not change what the other roles can open", () => {
    expect(routeAllowed("/audit", "field_worker")).toBe(false);
    expect(routeAllowed("/governance", "compliance")).toBe(false);
    expect(routeAllowed("/audit", "compliance")).toBe(true);
    expect(routeAllowed("/system-health", "engineer")).toBe(false);
  });
});
