import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SidebarContent } from "./app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/management",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// The rail's width is CSS driven off <html data-nav>; these tests assert the
// attribute and the stored preference, which are what the CSS reads.
describe("nav rail collapse", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-nav");
    localStorage.clear();
  });
  afterEach(() => {
    document.documentElement.removeAttribute("data-nav");
  });

  it("renders no toggle unless the rail is collapsible", () => {
    render(<SidebarContent role="engineer" user={null} />);
    expect(screen.queryByRole("button", { name: /navigation/i })).not.toBeInTheDocument();
  });

  it("collapses, persists, and expands again", async () => {
    render(<SidebarContent role="engineer" user={null} collapsible />);

    const collapse = screen.getByRole("button", { name: "Collapse navigation" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(collapse);
    // The attribute and localStorage are written synchronously by the click...
    expect(document.documentElement.getAttribute("data-nav")).toBe("collapsed");
    expect(localStorage.getItem("kairos-nav")).toBe("collapsed");

    // ...but the re-render arrives via MutationObserver, which is async. Awaiting
    // it is the point: it proves React actually observes the attribute rather
    // than tracking a duplicate copy in state.
    const expand = await screen.findByRole("button", { name: "Expand navigation" });
    expect(expand).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(expand);
    expect(document.documentElement.hasAttribute("data-nav")).toBe(false);
    expect(localStorage.getItem("kairos-nav")).toBe("expanded");
    await screen.findByRole("button", { name: "Collapse navigation" });
  });

  it("keeps exactly one toggle in the tree in both states", async () => {
    render(<SidebarContent role="engineer" user={null} collapsible />);
    expect(screen.getAllByRole("button", { name: /navigation/i })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Collapse navigation" }));
    await waitFor(() => expect(screen.getAllByRole("button", { name: /navigation/i })).toHaveLength(1));
  });

  it("names every rail link, so the icon-only rail stays readable to assistive tech", () => {
    render(<SidebarContent role="engineer" user={null} collapsible />);
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveAccessibleName();
    }
  });

  it("owns the global actions when given them: search, ingest, account", () => {
    const actions = { onSearch: vi.fn(), onCreate: vi.fn(), onOpenUser: vi.fn(), accountName: "avery@kairos.local", accountInitials: "AV" };
    render(<SidebarContent role="engineer" user={null} collapsible actions={actions} />);
    fireEvent.click(screen.getByRole("button", { name: "Search workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "Ingest document" }));
    fireEvent.click(screen.getByRole("button", { name: "Open user menu" }));
    expect(actions.onSearch).toHaveBeenCalledOnce();
    expect(actions.onCreate).toHaveBeenCalledOnce();
    expect(actions.onOpenUser).toHaveBeenCalledOnce();
    expect(screen.getByText("avery@kairos.local")).toBeInTheDocument();
  });
});
