"""
Cross-site failure patterns: the same failure family recurring on the same equipment class at more
than one site, or recurring at one site while a sister site runs the same class and has not seen it.

Read-only and model-free. The output is counts, failure families, equipment classes and site ids,
and nothing else: no description, no work-order text, no person. That is what lets a pattern cross a
site boundary without the PII redaction pass free text would need (ARCHITECTURE.md, Multi-Site Scale).
"""

from collections import defaultdict
from typing import Any

from api.utils.failure_families import failure_family

WINDOW_DAYS = 180
# One work order is an incident. Two in the same family is the threshold the recurring-failure
# detector already uses (`routers/events.py`), so a "pattern" means the same thing in both places.
MIN_EVENTS = 2


def find_patterns(work_orders: list[dict], assets: list[dict]) -> list[dict[str, Any]]:
    """Group work orders by (equipment class, failure family) and report each site's share.

    `work_orders` rows carry `asset_id`, `occurred_at` and `payload.failure_code`; `assets` rows carry
    `asset_id`, `equipment_class` and `site_id`. A work order whose asset is unknown, or whose code is
    blank, belongs to no pattern. A pattern is reported only when the class exists on two or more
    sites and at least one of them has reached `MIN_EVENTS`.
    """
    by_id = {a["asset_id"]: a for a in assets if a.get("equipment_class") and a.get("site_id")}
    fleet: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # class -> site -> assets
    for a in by_id.values():
        fleet[a["equipment_class"]][a["site_id"]] += 1

    seen: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for wo in work_orders:
        asset = by_id.get(wo.get("asset_id"))
        family = failure_family((wo.get("payload") or {}).get("failure_code"))
        if not asset or not family:
            continue
        site = seen[(asset["equipment_class"], family)].setdefault(
            asset["site_id"], {"events": 0, "assets": set(), "last_seen": ""}
        )
        site["events"] += 1
        site["assets"].add(asset["asset_id"])
        site["last_seen"] = max(site["last_seen"], wo.get("occurred_at") or "")

    patterns = []
    for (equipment_class, family), sites in seen.items():
        class_sites = fleet[equipment_class]
        if len(class_sites) < 2 or max(s["events"] for s in sites.values()) < MIN_EVENTS:
            continue
        rows = [
            {
                "site_id": site_id,
                "events": sites.get(site_id, {}).get("events", 0),
                "assets_affected": len(sites.get(site_id, {}).get("assets", ())),
                "assets_in_class": count,
                "last_seen": sites.get(site_id, {}).get("last_seen") or None,
            }
            for site_id, count in class_sites.items()
        ]
        rows.sort(key=lambda r: (-r["events"], r["site_id"]))
        patterns.append({
            "equipment_class": equipment_class,
            "failure_family": family,
            # "shared": seen at two or more sites. "advisory": one site has it, a sister site runs
            # the same class and has not seen it yet, which is the early warning.
            "kind": "shared" if sum(1 for r in rows if r["events"]) >= 2 else "advisory",
            "total_events": sum(r["events"] for r in rows),
            "sites": rows,
        })
    patterns.sort(key=lambda p: (p["kind"] != "shared", -p["total_events"], p["equipment_class"], p["failure_family"]))
    return patterns
