// Daily event counts by priority for the events chart (a module of its own: a Next page file may export nothing but the page).

const DAY_MS = 86_400_000;
export const CHART_DAYS = 14;
/** Events per day by priority for the CHART_DAYS ending on the newest event's day. Every day is
 *  present, with zeros, so a quiet day is a gap in the bars and not a point on a curve. */
export function dailyByPriority(rows: { occurred_at: string; priority: string }[]) {
  if (rows.length === 0) return [];
  const newest = Math.max(...rows.map((r) => Date.parse(r.occurred_at)));
  const endDay = Math.floor(newest / DAY_MS) * DAY_MS;
  const days = Array.from({ length: CHART_DAYS }, (_, i) => endDay - (CHART_DAYS - 1 - i) * DAY_MS);
  const index = new Map(days.map((d, i) => [d, i]));
  const buckets: Record<string, number | string>[] = days.map((d) => ({
    day: new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" }),
  }));
  for (const r of rows) {
    const i = index.get(Math.floor(Date.parse(r.occurred_at) / DAY_MS) * DAY_MS);
    if (i === undefined) continue;
    buckets[i][r.priority] = ((buckets[i][r.priority] as number | undefined) ?? 0) + 1;
  }
  return buckets;
}

