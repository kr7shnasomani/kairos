import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({ getMe: vi.fn() }));

import { renderHook, waitFor } from "@testing-library/react";
import { getMe } from "@/lib/auth";
import type { User } from "@/lib/types";
import { ADMIN_VIEW_ROLES, PROMOTE_ROLES, roleHome, routeAllowed, useRole, visibleTo } from "./use-role";

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

describe("useRole while loading", () => {
  it("is null until the profile answers, so no gated control flashes", async () => {
    let answer!: (u: User | null) => void;
    vi.mocked(getMe).mockReturnValueOnce(new Promise<User | null>((r) => { answer = r; }));
    const { result } = renderHook(() => useRole());

    expect(result.current).toBeNull();
    expect(visibleTo(PROMOTE_ROLES, result.current)).toBe(false);
    answer({ role: "field_worker" } as User);
    await waitFor(() => expect(result.current).toBe("field_worker"));
  });
});
