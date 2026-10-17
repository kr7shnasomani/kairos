import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SidebarContent } from "./app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/overview",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// The desktop rail is fixed: it has no collapse control (owner decision 2026-10-17). Below `lg`
// the same component opens as a drawer from the header's menu button instead.
describe("nav rail", () => {
  it("has no collapse or expand control", () => {
    const actions = { onSearch: vi.fn(), onCreate: vi.fn(), onOpenUser: vi.fn(), accountName: "avery@kairos.local", accountInitials: "AV" };
    render(<SidebarContent role="engineer" user={null} actions={actions} />);
    expect(screen.queryByRole("button", { name: /(collapse|expand) navigation/i })).not.toBeInTheDocument();
  });

  it("names every rail link, for assistive tech", () => {
    render(<SidebarContent role="engineer" user={null} />);
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveAccessibleName();
    }
  });

  it("owns the global actions when given them: search, ingest, account", () => {
    const actions = { onSearch: vi.fn(), onCreate: vi.fn(), onOpenUser: vi.fn(), accountName: "avery@kairos.local", accountInitials: "AV" };
    render(<SidebarContent role="engineer" user={null} actions={actions} />);
    fireEvent.click(screen.getByRole("button", { name: "Search workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "Ingest document" }));
    fireEvent.click(screen.getByRole("button", { name: "Open user menu" }));
    expect(actions.onSearch).toHaveBeenCalledOnce();
    expect(actions.onCreate).toHaveBeenCalledOnce();
    expect(actions.onOpenUser).toHaveBeenCalledOnce();
    expect(screen.getByText("avery@kairos.local")).toBeInTheDocument();
  });
});
