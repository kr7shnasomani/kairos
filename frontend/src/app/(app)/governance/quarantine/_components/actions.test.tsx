import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { QuarantineItem } from "@/lib/types";
import { ActionModals } from "./actions";

vi.mock("@/lib/api", () => ({
  promoteQuarantine: vi.fn(),
  disputeQuarantine: vi.fn(),
  requestQuarantineInfo: vi.fn(),
  resolveDeviationFlag: vi.fn(),
}));

const flag = { item_id: "q-1", asset_id: "EQ-101", input_type: "deviation_flag", review_status: "pending" } as QuarantineItem;

describe("resolve deviation", () => {
  afterEach(cleanup);

  it("offers only dismissal to a role that cannot promote", () => {
    // Confirming a deviation marks its quarantine item promoted, which the API allows reliability and admin only.
    render(<ActionModals item={flag} mode="resolve-deviation" busy={false} canConfirmDeviation={false} onClose={vi.fn()} run={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Confirm deviation" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not a deviation" })).toBeInTheDocument();
    expect(screen.getByText(/needs reliability or admin/)).toBeInTheDocument();
  });

  it("offers confirmation to a role that can promote", () => {
    render(<ActionModals item={flag} mode="resolve-deviation" busy={false} canConfirmDeviation onClose={vi.fn()} run={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Confirm deviation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not a deviation" })).toBeInTheDocument();
  });
});
