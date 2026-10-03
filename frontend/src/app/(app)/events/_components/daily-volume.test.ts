import { describe, expect, it } from "vitest";
import { CHART_DAYS, dailyByPriority } from "./daily-volume";

const at = (day: string, priority = "normal") => ({ occurred_at: `${day}T10:00:00Z`, priority });

describe("dailyByPriority", () => {
  it("has one bucket for each of the last CHART_DAYS days, zeros included, ending on the newest event", () => {
    const out = dailyByPriority([at("2026-10-03"), at("2026-09-28")]);
    expect(out).toHaveLength(CHART_DAYS);
    expect(out[CHART_DAYS - 1].normal).toBe(1); // 3 Oct, the newest
    expect(out[CHART_DAYS - 6].normal).toBe(1); // 28 Sept
    expect(out.filter((b) => b.normal === undefined)).toHaveLength(CHART_DAYS - 2); // quiet days stay empty
  });

  it("counts each priority separately and drops events older than the window", () => {
    const out = dailyByPriority([at("2026-10-03", "critical"), at("2026-10-03", "normal"), at("2026-10-03", "normal"), at("2026-08-01")]);
    expect(out[CHART_DAYS - 1]).toMatchObject({ critical: 1, normal: 2 });
    expect(out.reduce((n, b) => n + ((b.normal as number) ?? 0) + ((b.critical as number) ?? 0), 0)).toBe(3);
  });

  it("is empty when there are no events", () => {
    expect(dailyByPriority([])).toEqual([]);
  });
});
