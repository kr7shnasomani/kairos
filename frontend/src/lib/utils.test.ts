import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { localDateString, parseLocalDate, relativeTime, slaCountdown } from "./utils";

const NOW = new Date("2026-07-14T12:00:00Z").getTime();

describe("relativeTime", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW); });
  afterEach(() => vi.useRealTimers());

  it("labels the past as before now", () => {
    expect(relativeTime("2026-07-14T11:59:40Z")).toBe("just now");
    expect(relativeTime("2026-07-14T09:00:00Z")).toBe("3h ago");
    expect(relativeTime("2026-07-11T12:00:00Z")).toBe("3d ago");
  });

  it("labels the future instead of calling it just now", () => {
    expect(relativeTime("2026-07-14T12:30:00Z")).toBe("in 30m");
    expect(relativeTime("2026-07-14T15:00:00Z")).toBe("in 3h");
    expect(relativeTime("2026-07-17T12:00:00Z")).toBe("in 3d");
  });

  it("returns an empty string for garbage", () => {
    expect(relativeTime("not a date")).toBe("");
  });
});

describe("slaCountdown", () => {
  it("counts down hours then days", () => {
    expect(slaCountdown("2026-07-14T14:00:00Z", NOW)).toEqual({ label: "2h left", tone: "text-danger" });
    expect(slaCountdown("2026-07-15T00:00:00Z", NOW)).toEqual({ label: "12h left", tone: "text-caution" });
    expect(slaCountdown("2026-07-17T12:00:00Z", NOW)).toEqual({ label: "3d left", tone: "text-muted" });
  });

  it("says overdue past the deadline, never a negative count", () => {
    expect(slaCountdown("2026-07-14T08:00:00Z", NOW)).toEqual({ label: "overdue", tone: "text-danger" });
  });
});

describe("local dates", () => {
  it("parses a date-only string as local midnight, not UTC", () => {
    const d = parseLocalDate("2026-07-14");
    expect([d.getFullYear(), d.getMonth(), d.getDate(), d.getHours()]).toEqual([2026, 6, 14, 0]);
  });

  it("formats a Date as its local calendar day", () => {
    expect(localDateString(new Date(2026, 6, 14, 0, 30))).toBe("2026-07-14");
    expect(localDateString(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });
});
