"""Ninety days of showcase plant life: events, briefs, governance records, knowledge capture and
plant states, all relative to an anchor (the load time), so the plant never ages.

Everything returned is a plain row dict for the table named in its list, with the showcase markers
already on it (a `DEMO-` asset id, a showcase site, a `DEMO-` person). `Showcase.audit_markers()`
re-checks that, and `tests/test_showcase_dataset.py` fails if a row carries none.

Two kinds of event:
  * `history_events` are direct rows (and graph `Event` nodes): the plant's past. They do not run the
    brief assembler, which would mint stale briefs for old events.
  * `live_events` go through the real event API on load, so a few current briefs, including a permit
    waiting for its second signature, are assembled by the real code.
"""

import json
import random
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from api.services.tenant import DEMO_GENERAL_ASSET, DEMO_PREFIX, is_demo_id, is_demo_site
from api.utils.failure_families import failure_family
from scripts.showcase.docs import CHAINS, CONFLICTS, DESC
from scripts.showcase.spec import EXPERTS, PERSON, SITE_A, SITE_B, SITE_NAME, Asset

IST = timedelta(hours=5, minutes=30)

# Failure codes grouped as `utils/failure_families.py` groups them, so recurrence is real.
SEAL = ("SEAL-FAIL", "LEAK-MECH")
MECH = ("BEARING-FAIL", "VIBE-HIGH", "MISALIGN")
PROC = ("LOW-FLOW", "HIGH-TEMP", "PRESSURE-LOSS")
CLOSE = (
    "Replaced the worn part, ran the equipment for one hour and checked for leaks.",
    "Cleaned and adjusted, no further action. Monitoring for one week.",
    "Part replaced from stores. Root cause noted in the work order for the reliability engineer.",
    "Tested satisfactory after repair. Returned to service.",
)
OBSERVATIONS = (
    "Noticed a faint smell of product near the pump base during rounds. Could be a small seal weep, not sure yet.",
    "Pressure gauge on the discharge line reads a little low compared with the panel. Might be the gauge, not the pump.",
    "Paint blistering on the lower shell. Looks cosmetic but it is new since the last turnaround.",
    "Lagging is damp at the elbow after the heavy rain. Wanted it written down in case it points to a leak.",
    "The standby pump started rough this morning. It settled after a few minutes but I want someone to listen to it.",
    "Gland drip rate looks higher than last week. Still within what I would call normal.",
    "Sample cooler is running warm. Cooling water flow might be restricted.",
)


@dataclass
class Showcase:
    assets: list[Asset]
    anchor: datetime
    history_events: list[dict] = field(default_factory=list)  # operational_events rows
    live_events: list[tuple[str, dict]] = field(default_factory=list)  # (API route, body)
    briefs: list[dict] = field(default_factory=list)
    brief_feedback: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    moc_items: list[dict] = field(default_factory=list)
    quarantine: list[dict] = field(default_factory=list)
    elicitation_sessions: list[dict] = field(default_factory=list)
    offboarding_sessions: list[dict] = field(default_factory=list)
    offboarding_items: list[dict] = field(default_factory=list)
    plant_states: list[dict] = field(default_factory=list)
    aliases: list[dict] = field(default_factory=list)

    def tables(self) -> dict[str, list[dict]]:
        return {
            "operational_events": self.history_events, "briefs": self.briefs, "brief_feedback": self.brief_feedback,
            "knowledge_conflicts": self.conflicts, "moc_items": self.moc_items, "quarantine_items": self.quarantine,
            "elicitation_sessions": self.elicitation_sessions, "offboarding_sessions": self.offboarding_sessions,
            "offboarding_session_items": self.offboarding_items, "plant_operating_states": self.plant_states,
            "asset_alias_map": self.aliases,
        }


def _uid(*parts: str) -> str:
    """A deterministic id from what the row is, so a re-run of the load meets the rows it wrote before
    (and ignores them) instead of adding a second copy."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "showcase:" + ":".join(parts)))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def pending_id(file_name: str) -> str:
    """The stand-in for a document's id until the document is in the vault. Written into the dataset files
    as it is, and swapped for the real id when the loader binds the dataset (`files.bind`)."""
    return f"DOC-PENDING-{zlib.crc32(file_name.encode()) % 10**8:08d}"


def _wid(prefix: str, n: int) -> str:
    return f"{prefix}-DEMO-{n:04d}"


def build_showcase(assets: list[Asset], anchor: datetime, demo_user_id: str, doc_ids: dict[str, str] | None = None,
                   seed: int = 20261003) -> Showcase:
    rng = random.Random(seed)
    sc = Showcase(assets=assets, anchor=anchor)
    docs = doc_ids or {}

    def doc(name: str) -> str:
        return docs.get(name) or pending_id(name)

    by_tag = {a.tag: a for a in assets}
    equipment = [a for a in assets if a.equipment_class not in ("process_unit",)]
    rotating = [a for a in equipment if "pump" in a.equipment_class or "compressor" in a.equipment_class]
    site_a_eq = [a for a in equipment if a.site_id == SITE_A]

    def at(days_ago: float, hour: int | None = None) -> datetime:
        """A time `days_ago` before the anchor, in local working hours unless an hour is given."""
        base = anchor - timedelta(days=days_ago)
        h = hour if hour is not None else rng.randint(5, 17)
        local = base.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=h, minutes=rng.randint(0, 59))
        return local - IST

    n_wo = n_ins = n_alarm = n_ptw = n_tag = n_shift = n_comp = 0
    techs = [PERSON[k].name for k in ("tech-1", "tech-2", "tech-3", "tech-4")]

    def event(etype: str, source: str, site: str, asset: str | None, payload: dict, when: datetime, subtype=None,
              compound: str | None = None) -> dict:
        eid = f"{DEMO_PREFIX}EVT-{etype.upper()[:6]}-{len(sc.history_events) + 1:04d}"
        body = {**payload, "event_id": eid, "event_type": etype, "source_system": source, "site_id": site,
                "occurred_at": _iso(when), "received_at": _iso(when + timedelta(minutes=2))}
        if asset and "asset_id" not in body and "asset_ids" not in body:
            body["asset_id"] = asset
        row = {"event_id": eid, "event_type": etype, "source_system": source, "site_id": site, "asset_id": asset,
               "payload": body, "occurred_at": _iso(when), "received_at": _iso(when + timedelta(minutes=2)),
               "redis_stream_id": None, "compound_event_id": compound, "event_subtype": subtype}
        sc.history_events.append(row)
        return row

    # --- Work orders, with deliberate recurring chains ----------------------------------------
    chains = CHAINS  # (tag, failure codes, days ago per occurrence), shared with the history cards in docs.py
    scheduled: list[tuple[float, str, str]] = []
    for tag, codes, days in chains:
        for i, d in enumerate(days):
            scheduled.append((d, tag, codes[i % len(codes)]))
    # Every piece of equipment has at least one work order, and some have more, so no asset page has an empty timeline.
    singles = list(equipment) + rng.sample(equipment, 60)
    for a in singles:
        code = rng.choice(list(DESC))
        scheduled.append((rng.uniform(1, 88), a.tag, code))
    scheduled.sort(reverse=True)
    seen: dict[tuple[str, str], int] = {}
    for days_ago, tag, code in scheduled:
        a = by_tag[tag]
        n_wo += 1
        fam = (tag, failure_family(code))
        seen[fam] = seen.get(fam, 0) + 1
        expert = next((e[0] for e in EXPERTS if (("pump" in a.equipment_class and e[3].startswith("pumps"))
                                                  or ("heater" in a.equipment_class and "heaters" in e[3])
                                                  or ("compressor" in a.equipment_class and "compressors" in e[3]))), None)
        tech = expert if (expert and rng.random() < 0.6) else rng.choice(techs)
        when = at(days_ago)
        pri = "high" if seen[fam] > 1 or a.criticality == "safety_critical" else rng.choice(("normal", "normal", "low"))
        event("work_order_created", "CMMS", a.site_id, a.asset_id, {
            "work_order_id": _wid("WO", n_wo), "failure_code": code, "description": DESC[code], "priority": pri,
            "assigned_technician_id": tech, "planned_start": None, "close_notes": rng.choice(CLOSE) if days_ago > 3 else None,
        }, when, subtype="recurring" if seen[fam] > 1 else None)

    # --- Inspections, alarms, permits, tag-outs, shift handovers -------------------------------
    inspectable = list(equipment)  # every asset is inspected at least once; a few are inspected again
    for a in inspectable + rng.sample(inspectable, 40):
        n_ins += 1
        result = rng.choices(("passed", "conditional", "failed"), (0.72, 0.2, 0.08))[0]
        event("inspection_complete", "EAM_INSPECTION", a.site_id, a.asset_id, {
            "inspection_type": rng.choice(("visual", "thickness", "functional test", "calibration check")),
            "result": result, "performed_by": PERSON["ins-1"].name, "document_id": None, "confidence": 0.85,
            "findings": {"passed": "No findings.", "conditional": "Minor findings, follow-up scheduled.",
                         "failed": "Finding outside acceptance criteria, work order raised."}[result],
        }, at(rng.uniform(1, 89)))
    for _ in range(110):
        a = rng.choice(rotating + [x for x in equipment if x.criticality == "safety_critical"])
        n_alarm += 1
        sev = rng.choices(("critical", "high", "medium", "low"), (0.1, 0.25, 0.4, 0.25))[0]
        event("alarm_acknowledged", "DCS", a.site_id, a.asset_id, {
            "alarm_id": _wid("ALM", n_alarm), "alarm_tag": f"{a.tag}-AL", "severity": sev,
            "alarm_description": rng.choice(("High vibration", "Low flow", "High temperature", "Level deviation", "Seal pot level low")),
            "acknowledged_by": PERSON[rng.choice(("shift-a", "shift-b", "shift-c"))].name,
        }, at(rng.uniform(0.5, 89)))
    ptw_assets = [by_tag[t] for t in ("P-1101A", "P-1101B", "K-2101A", "K-2101B", "H-1101", "T-6103", "B-3101", "P-2101A", "E-1102")]
    for i in range(40):
        a = ptw_assets[i % len(ptw_assets)]
        n_ptw += 1
        boundary = [a.asset_id] + [x.asset_id for x in equipment if x.parent == a.parent and x.equipment_class.startswith("valve")][:2]
        event("ptw_generated", "PTW_WORKFLOW", a.site_id, a.asset_id, {
            "ptw_id": _wid("PTW", n_ptw), "ptw_type": rng.choice(("isolation", "hot_work", "confined_space", "high_pressure_line")),
            "work_area": f"{a.unit} unit", "asset_ids": boundary,
            "issuing_engineer_id": PERSON[rng.choice(("eng-1", "eng-2", "rel-1"))].name,
        }, at(rng.uniform(2, 88)))
    for _ in range(24):
        a = rng.choice(site_a_eq)
        n_tag += 1
        event("equipment_tag_out", "CMMS", a.site_id, a.asset_id, {
            "tag_out_reason": rng.choice(("Seal replacement", "Bearing replacement", "Calibration", "Inspection access")),
            "performed_by": rng.choice(techs), "expected_return_date": _iso(anchor + timedelta(days=rng.randint(1, 6))),
        }, at(rng.uniform(1, 80)))
    leads = ("shift-a", "shift-b", "shift-c")
    for d in range(30, 0, -1):
        for s, hour in enumerate((6, 14, 22)):
            site = SITE_A if (d + s) % 6 else SITE_B
            n_shift += 1
            out_l, in_l = leads[s % 3], leads[(s + 1) % 3]
            when = at(d, hour)
            event("shift_handover", "SHIFT_SCHEDULING", site, None, {
                "outgoing_shift_lead_id": PERSON[out_l].name, "incoming_shift_lead_id": PERSON[in_l].name,
                "handover_time": _iso(when),
            }, when)
    # Compound events: one physical happening seen by two systems. Three keep close clocks, three drift.
    for i, drift_min in enumerate((3, 5, 12, 74, 92, 118)):
        a = rng.choice(rotating)
        n_comp += 1
        cid = _uid("compound", str(n_comp))
        when = at(rng.uniform(3, 60))
        event("work_order_created", "CMMS", a.site_id, a.asset_id, {
            "work_order_id": _wid("WO", 900 + n_comp), "failure_code": "VIBE-HIGH", "description": DESC["VIBE-HIGH"],
            "priority": "high", "assigned_technician_id": rng.choice(techs), "planned_start": None, "close_notes": None,
        }, when, compound=cid)
        event("alarm_acknowledged", "DCS", a.site_id, a.asset_id, {
            "alarm_id": _wid("ALM", 900 + n_comp), "alarm_tag": f"{a.tag}-VIB", "severity": "high",
            "alarm_description": "High vibration", "acknowledged_by": PERSON["shift-a"].name,
        }, when + timedelta(minutes=drift_min), compound=cid)
    sc.history_events.sort(key=lambda r: r["occurred_at"])

    # --- Live events: run through the real API on load ----------------------------------------
    now = anchor
    live = [
        ("/events/work-order", {"source_system": "CMMS", "site_id": SITE_A, "work_order_id": _wid("WO", 800),
                                "asset_id": by_tag["P-1101A"].asset_id, "failure_code": "SEAL-FAIL",
                                "description": DESC["SEAL-FAIL"], "priority": "critical",
                                "assigned_technician_id": demo_user_id,
                                "occurred_at": _iso(now - timedelta(hours=3))}),
        ("/events/work-order", {"source_system": "CMMS", "site_id": SITE_A, "work_order_id": _wid("WO", 801),
                                "asset_id": by_tag["K-2101A"].asset_id, "failure_code": "VIBE-HIGH",
                                "description": DESC["VIBE-HIGH"], "priority": "high",
                                "assigned_technician_id": demo_user_id,
                                "occurred_at": _iso(now - timedelta(hours=7))}),
        ("/events/work-order", {"source_system": "CMMS", "site_id": SITE_B, "work_order_id": _wid("WO", 802),
                                "asset_id": by_tag["P-6101C"].asset_id, "failure_code": "BEARING-FAIL",
                                "description": DESC["BEARING-FAIL"], "priority": "high",
                                "assigned_technician_id": PERSON["tech-1"].name,
                                "occurred_at": _iso(now - timedelta(hours=11))}),
        ("/events/ptw", {"source_system": "PTW_WORKFLOW", "site_id": SITE_A, "ptw_id": _wid("PTW", 800),
                         "work_area": "CDU pump house",
                         "asset_ids": [by_tag["P-1101A"].asset_id, by_tag["XV-1101"].asset_id, by_tag["XV-1102"].asset_id],
                         "ptw_type": "isolation", "issuing_engineer_id": demo_user_id,
                         "occurred_at": _iso(now - timedelta(hours=2, minutes=40))}),
        ("/events/ptw", {"source_system": "PTW_WORKFLOW", "site_id": SITE_A, "ptw_id": _wid("PTW", 801),
                         "work_area": "HDT compressor house",
                         "asset_ids": [by_tag["K-2101A"].asset_id, by_tag["XV-2101"].asset_id],
                         "ptw_type": "high_pressure_line", "issuing_engineer_id": demo_user_id,
                         "occurred_at": _iso(now - timedelta(hours=6, minutes=15))}),
        ("/events/alarm", {"source_system": "DCS", "site_id": SITE_A, "alarm_id": _wid("ALM", 800),
                           "asset_id": by_tag["H-1101"].asset_id, "alarm_tag": "TT-1102-HH", "severity": "critical",
                           "alarm_description": "Heater outlet temperature high high",
                           "acknowledged_by": PERSON["shift-a"].name, "occurred_at": _iso(now - timedelta(hours=1, minutes=10))}),
        ("/events/shift-handover", {"source_system": "SHIFT_SCHEDULING", "site_id": SITE_A,
                                    "outgoing_shift_lead_id": PERSON["shift-a"].name,
                                    "incoming_shift_lead_id": demo_user_id,
                                    "handover_time": _iso(now - timedelta(minutes=50)),
                                    "occurred_at": _iso(now - timedelta(minutes=50))}),
        ("/events/tag-out", {"source_system": "CMMS", "site_id": SITE_B, "asset_id": by_tag["P-6101C"].asset_id,
                             "tag_out_reason": "Bearing replacement", "performed_by": PERSON["tech-1"].name,
                             "occurred_at": _iso(now - timedelta(hours=10))}),
        ("/events/inspection-complete", {"source_system": "EAM_INSPECTION", "site_id": SITE_A,
                                         "asset_id": by_tag["PSV-1102"].asset_id, "inspection_type": "bench test",
                                         "result": "conditional", "performed_by": PERSON["ins-1"].name,
                                         "findings": "Re-test after seat lapping within tolerance, monitor next quarter.",
                                         "confidence": 0.85, "occurred_at": _iso(now - timedelta(hours=5))}),
    ]
    sc.live_events = live

    # --- Plant states -------------------------------------------------------------------------
    for site, steps in ((SITE_A, (("normal", 90, 62), ("turnaround", 62, 48), ("normal", 48, None))),
                        (SITE_B, (("normal", 90, 33), ("shutdown", 33, 31), ("normal", 31, None)))):
        for state, start, end in steps:
            sc.plant_states.append({
                "id": _uid("plant", site, state, str(start)), "site_id": site, "state": state, "set_by": PERSON["eng-1"].name,
                "set_at": _iso(anchor - timedelta(days=start)),
                "expires_at": _iso(anchor - timedelta(days=end)) if end else None,
            })

    # --- Aliases: every tag resolves, a few legacy names, and some candidates awaiting review ---
    for a in assets:
        sc.aliases.append({"canonical_asset_id": a.asset_id, "alias": a.tag, "alias_source": "showcase:equipment_register",
                           "confidence": 1.0, "confirmed": True, "confirmed_by": "showcase-loader"})
        # The name as the header of every document spells it: "Crude preheat exchanger 5" is read as a tag, and
        # resolves to the asset only if the name is a confirmed alias too.
        sc.aliases.append({"canonical_asset_id": a.asset_id, "alias": a.name, "alias_source": "showcase:equipment_register",
                           "confidence": 1.0, "confirmed": True, "confirmed_by": "showcase-loader"})
        for alias in a.aliases:
            sc.aliases.append({"canonical_asset_id": a.asset_id, "alias": f"{alias} ({a.site_id})",
                               "alias_source": "showcase:legacy_nomenclature", "confidence": 0.98, "confirmed": True,
                               "confirmed_by": "showcase-loader"})
    for tag, cand, conf in (("P-1103A", "Bottoms transfer A", 0.78), ("P-1103B", "Bottoms transfer B", 0.74),
                            ("E-1103", "Third preheater", 0.66), ("V-1102", "Reflux accumulator", 0.82),
                            ("XV-2101", "Reactor ESD 1", 0.71), ("T-6104", "Tank 4 (spare)", 0.69)):
        sc.aliases.append({"canonical_asset_id": by_tag[tag].asset_id, "alias": f"{cand} ({by_tag[tag].site_id})",
                           "alias_source": "extraction:ner_candidate", "confidence": conf, "confirmed": False,
                           "confirmed_by": None})

    _governance(sc, by_tag, doc, rng, anchor)
    _briefs(sc, by_tag, doc, rng, anchor, demo_user_id)
    _knowledge_capture(sc, by_tag, rng, anchor)
    return sc


def _governance(sc: Showcase, by_tag, doc, rng, anchor):
    # Conflicts, with the two sources the procedure and the bulletin gave, and MoC records for the
    # engineering ones that were routed to Management of Change.
    sla_hours = {"engineering": 24, "administrative": 120}
    moc_n = 0
    ages = [26, 24, 22, 20, 19, 17, 14, 12, 40, 8]
    for c, age in zip(CONFLICTS, ages, strict=True):
        a = by_tag[c.asset_tag]
        created = anchor - timedelta(days=age)
        cid = _uid("conflict", c.key)
        resolved = c.status == "resolved"
        sc.conflicts.append({
            "conflict_id": cid, "track": c.track, "asset_id": a.asset_id, "parameter": c.parameter,
            "source_a": {"value": f"{c.old} {c.unit}", "origin": "operating procedure", "file_name": c.sop_file,
                         "document_id": doc(c.sop_file), "authority_level": 4},
            "source_b": {"value": f"{c.new} {c.unit}", "origin": "manufacturer service bulletin", "file_name": c.bulletin_file,
                         "document_id": doc(c.bulletin_file), "authority_level": 3},
            "authority_a": 4, "authority_b": 3, "severity": c.severity, "status": c.status,
            "sla_deadline": _iso(created + timedelta(hours=sla_hours[c.track])),
            "escalated_at": _iso(created + timedelta(hours=sla_hours[c.track], minutes=5)) if not resolved and age > 6 else None,
            "escalated_to": "reliability_engineer" if not resolved and age > 6 else None,
            "resolved_by": PERSON["rel-1"].name if resolved else None,
            "resolved_at": _iso(created + timedelta(days=3)) if resolved else None,
            "created_at": _iso(created),
        })
        if c.track == "engineering" and c.status in ("pending_moc", "resolved"):
            moc_n += 1
            status = "approved" if resolved else ("pending_approval" if c.key == "c01" else "draft")
            sc.moc_items.append({
                "moc_id": f"MOC-DEMO-{moc_n:04d}", "conflict_id": cid, "asset_id": a.asset_id,
                "description": (f"{c.asset_tag} {c.parameter.replace('_', ' ')}: the manufacturer bulletin revises the value to "
                                f"{c.new} {c.unit}; the operating procedure still states {c.old} {c.unit}. "
                                "Update the procedure and re-check dependent records."),
                "conflicting_sources": [{"value": f"{c.old} {c.unit}", "document_id": doc(c.sop_file)},
                                        {"value": f"{c.new} {c.unit}", "document_id": doc(c.bulletin_file)}],
                "blast_radius": [doc(c.sop_file)], "status": status,
                "approved_by": PERSON["eng-2"].name if status == "approved" else None,
                "approved_at": _iso(created + timedelta(days=3)) if status == "approved" else None,
                "created_at": _iso(created + timedelta(hours=2)),
            })
    sc.moc_items.append({
        "moc_id": f"MOC-DEMO-{moc_n + 1:04d}", "conflict_id": None, "asset_id": by_tag["P-1102A"].asset_id,
        "description": "Proposed change of the reflux pump seal flush plan from API Plan 11 to Plan 53B. Rejected: the "
                       "existing plan meets the duty and the change needs a shutdown.",
        "conflicting_sources": [], "blast_radius": [], "status": "rejected", "approved_by": None, "approved_at": None,
        "created_at": _iso(anchor - timedelta(days=45)),
    })

    # Quarantine: every input type, some overdue, some reviewed.
    def q(asset_tag, itype, content, submitter, age_h, status="pending", ctx=None, reviewer=None, wo=None, sla_h=120):
        a = by_tag[asset_tag] if asset_tag else None
        submitted = anchor - timedelta(hours=age_h)
        sc.quarantine.append({
            "item_id": _uid("quarantine", str(len(sc.quarantine)), itype),
            "asset_id": a.asset_id if a else DEMO_GENERAL_ASSET, "content": content, "input_type": itype,
            "submitted_by": submitter, "submitted_at": _iso(submitted), "reviewer_id": reviewer,
            "review_status": status, "reviewed_at": _iso(submitted + timedelta(hours=30)) if reviewer else None,
            "work_order_id": wo, "session_context": ctx or {}, "sla_due_at": _iso(submitted + timedelta(hours=sla_h)),
            "escalated_at": _iso(submitted + timedelta(hours=sla_h, minutes=3)) if age_h > sla_h else None,
        })

    deviations = [
        ("XV-1101", "Isolation valve XV-1101 handwheel is mounted on the opposite side to the P&ID. Operators may close the wrong one in an emergency."),
        ("PSV-1102", "Relief valve PSV-1102 discharge line has an extra elbow that is not on the drawing."),
        ("P-1103A", "Pump P-1103A suction strainer is missing from the as-built line."),
        ("V-2102", "Level glass on V-2102 is fitted with a different range from the one in the data sheet."),
        ("XV-6101", "Tank outlet valve XV-6101 has a bypass that is not shown on the tank farm P&ID."),
        ("E-1104", "Exchanger E-1104 vent is plumbed to the open drain, drawing shows the closed drain."),
    ]
    for i, (tag, text) in enumerate(deviations):
        status = "pending" if i < 4 else ("disputed" if i == 4 else "archived")
        q(tag, "deviation_flag", text, PERSON[("tech-1", "tech-2", "tech-3")[i % 3]].name, 150 - i * 21, status,
          {"reason": "physical deviation from drawing"}, PERSON["rel-1"].name if status != "pending" else None, sla_h=24)
    voice = [
        ("P-1101A", "Yeah so when I pulled the seal this time the face wear was heavier on one side. It looked like the pump had been running at low flow for a while, I think the minimum flow valve is not opening fully when the flow drops."),
        ("K-2101A", "The compressor has been louder than normal at night for about two weeks, a kind of knock at the second stage. The vibration gauge is still green so I did not raise it."),
        ("FV-1103", "That control valve sticks on small moves, I have been nudging it by hand during the night shift. The positioner looks fine, I think it is the packing."),
        ("P-3101B", "Bearing housing on the standby cooling water pump runs hotter than its sister pump. Same oil, same load. I would swap the bearing next time it is down."),
        ("T-6102", "The radar gauge on tank six one oh two reads about ten millimetres above the dip. It has done that since the last calibration."),
        ("E-1107A", "Overhead condenser outlet temperature is creeping up. Probably fouling, we last cleaned it before the monsoon."),
    ]
    for i, (tag, text) in enumerate(voice):
        q(tag, "voice_note", text, PERSON[("tech-1", "tech-2", "shift-a")[i % 3]].name, 200 - i * 26,
          "disputed" if i == 4 else "pending",
          {"language": "en", "confidence": 0.86 - i * 0.03, "filename": f"voice-note-{i + 1}.wav"},
          PERSON["rel-2"].name if i == 4 else None, wo=f"WO-DEMO-{40 + i:04d}")
    for i, text in enumerate(OBSERVATIONS):
        tag = ("P-1102B", "P-1104A", "C-1101", "E-1105", "P-1101B", "P-6101A", "E-1106")[i]
        q(tag, "field_observation", text, PERSON[("tech-2", "shift-b", "tech-4")[i % 3]].name, 90 - i * 11,
          "pending" if i != 5 else "archived", {}, PERSON["rel-1"].name if i == 5 else None)
    elic = [
        ("P-1101A", ["Was the barrier fluid level normal before the seal failed?", "What was the discharge flow in the hour before the failure?"],
         ["The barrier pot level had been dropping slowly for about a week.", "Flow was around 95 cubic metres an hour, below what the manual says is the minimum."], "WO-DEMO-0042"),
        ("K-2101A", ["What did the vibration trend look like in the week before the alarm?", "Was anything changed on the lube oil system?"],
         ["It crept up about a millimetre per second a day.", "We changed the oil filter two weeks earlier."], "WO-DEMO-0044"),
        ("P-3101B", ["How long did the standby pump run before the bearing alarm?", "Was the pump alignment checked after the last overhaul?"],
         ["It had run about nine days.", "We checked it cold but not hot. The thermal growth may have thrown it off."], "WO-DEMO-0047"),
        ("FV-1103", ["Did the deadband change after the packing was tightened?", "How often has the valve been stroked by hand?"],
         ["Yes, it improved for a few days and then came back.", "Most nights, I would say."], "WO-DEMO-0051"),
    ]
    for i, (tag, qs, ans, wo) in enumerate(elic):
        content = [{"question_index": j, "question": qq, "answer": aa} for j, (qq, aa) in enumerate(zip(qs, ans, strict=True))]
        q(tag, "elicitation_response", json.dumps(content), PERSON[("tech-1", "tech-2")[i % 2]].name, 110 - i * 19,
          "pending", {"questions": qs, "work_order_id": wo}, wo=wo)
    off = [
        ("pumps and seals", ["Which pump on the plant is the most sensitive to running below minimum flow, and how can you tell?"],
         ["P-1101A. The seal pot level drops and the gland warms up in the first ten minutes."], "DEMO-EXPERT-SKHANNA"),
        ("heaters", ["What do you watch first when a heater pass flow trips?"],
         ["The skin thermocouples on the third pass. They move before the outlet temperature does."], "DEMO-EXPERT-MDALAL"),
    ]
    for i, (fam, qs, ans, person) in enumerate(off):
        content = [{"question_index": 0, "answer": ans[0]}]
        q(None, "offboarding_response", json.dumps(content), PERSON["rel-1"].name, 60 - i * 15, "pending",
          {"questions": qs, "equipment_family": fam.upper(), "personnel_id": person})


def _briefs(sc: Showcase, by_tag, doc, rng, anchor, demo_user_id):
    def brief(trigger, tag, headline, body, priority, age_h, actions=(), warnings=(), source_files=(),
              ack=None, requires_cs=False, countersigned=None, recipient=None, conf=0.88, wo=None, ptw=None):
        a = by_tag[tag] if tag else None
        created = anchor - timedelta(hours=age_h)
        brief_id = _uid("brief", str(len(sc.briefs)), trigger)
        etype = {"work_order": "work_order_created", "recurring_failure_detected": "work_order_created",
                 "ptw": "ptw_generated", "alarm": "alarm_acknowledged", "shift_handover": "shift_handover"}[trigger]
        trigger_event = next((e["event_id"] for e in reversed(sc.history_events)
                              if e["event_type"] == etype and (a is None or e["asset_id"] == a.asset_id)), None)
        sources = [{"document_id": doc(f), "document_type": "procedure", "title": f.rsplit(".", 1)[0].replace("-", " "),
                    "authority_level": 3 if f.startswith(("HFS", "NWC", "THX", "SVW", "KHT", "OTS", "MLS", "CLC")) else 4,
                    "relevant_excerpt": "See the cited document.", "vault_url": None, "is_quarantine": False}
                   for f in source_files]
        sc.briefs.append({
            "brief_id": brief_id, "trigger_event_id": trigger_event,
            "trigger_event_type": trigger, "asset_id": a.asset_id if a else DEMO_GENERAL_ASSET,
            "recipient_user_id": recipient or demo_user_id, "priority": priority, "headline": headline, "body": body,
            "action_items": list(actions), "warnings": list(warnings), "quarantine_flags": [], "sources": sources,
            "confidence": conf, "work_order_id": wo, "ptw_id": ptw, "delivery_frozen": False,
            "requires_countersignature": requires_cs, "delivered_at": _iso(created + timedelta(minutes=35)),
            "acknowledged_at": _iso(created + timedelta(hours=2)) if ack else None,
            "acknowledged_by": ack, "countersigned_by": countersigned,
            "countersigned_at": _iso(created + timedelta(hours=3)) if countersigned else None,
            "created_at": _iso(created),
        })
        return brief_id

    specs = [
        ("work_order", "P-1101A", "Seal failure on P-1101A: this is the fourth in 84 days", "P-1101A has failed with a seal fault four times since the last overhaul, each about three weeks apart. The pump manual states a minimum continuous flow of 120 m3/h and the latest bulletin raises it to 150 m3/h; the recorded flow before each failure was below both.", "critical", 6, ["Check the minimum flow bypass opens below 150 m3/h", "Use seal HAL-MS-4471 revision B", "Raise a reliability review of the pump duty"], ["Procedure SOP-CDU-crude-feed-pump-operation.pdf still states 120 m3/h"], ["HFS-CP-manual-crude-feed-pumps.pdf", "HFS-SB-2026-05-minimum-flow.pdf", "SOP-CDU-crude-feed-pump-operation.pdf"], None, "WO-DEMO-0800", None),
        ("recurring_failure_detected", "P-3101B", "Recurring bearing failures on P-3101B", "Three bearing faults on cooling water pump P-3101B in 77 days. The bearing condition report for its sister pump shows 78 degC at rated load; the bulletin lowers the alarm to 80 degC.", "high", 30, ["Check alignment hot, not only cold", "Compare with P-3101A bearing temperature"], [], ["INSP-P-3101A-bearing-condition.pdf", "HFS-SB-2026-02-bearing-temperature.pdf"], PERSON["shift-b"].name, None, None),
        ("work_order", "K-2101A", "High vibration on recycle compressor K-2101A", "Frame vibration alarm on K-2101A. The manual alarm is 12 mm/s and trip 18 mm/s. The discharge temperature trip is 130 degC in the manual, 135 degC in the operating procedure and 125 degC in the latest bulletin; confirm which applies before changing setpoints.", "high", 8, ["Hold the discharge temperature below 125 degC until the conflict is resolved", "Inspect second stage valves"], ["Three sources disagree on the discharge temperature trip"], ["NWC-RC-manual-recycle-gas-compressors.pdf", "NWC-SB-2026-09-discharge-temperature.pdf", "SOP-HDT-recycle-compressor-start.pdf"], None, "WO-DEMO-0801", None),
        ("ptw", "P-1101A", "Permit PTW-DEMO-0800: isolation of P-1101A for seal replacement", "Isolation boundary: P-1101A suction and discharge, XV-1101 and XV-1102. Both emergency isolation valves passed their last stroke tests. Two signatures are required: the receiver acknowledges, a second authority countersigns.", "critical", 3, ["Verify the lock-out on the motor breaker", "Confirm the casing is drained", "Second signature needed before work starts"], ["Do not start work on one signature"], ["SOP-CDU-isolation-and-lockout.pdf", "INSP-XV-1102-stroke-test.pdf"], PERSON["eng-1"].name, "PTW-DEMO-0800", None),
        ("ptw", "K-2101A", "Permit PTW-DEMO-0438: valve change on K-2101A", "Isolation boundary: K-2101A, XV-2101 and XV-2102. The compressor is depressurised and purged. Fully signed and closed out.", "high", 150, ["Close out the permit after the leak test"], [], ["INSP-K-2101A-valve-inspection.pdf"], PERSON["eng-2"].name, "PTW-DEMO-0438", PERSON["rel-1"].name),
        ("alarm", "H-1101", "High high alarm on heater outlet temperature", "H-1101 outlet temperature reached the high high alarm. The hottest tube skin reading in the last survey was 588 degC; the procedure limit is 620 degC and the latest bulletin sets 595 degC.", "critical", 2, ["Reduce firing", "Check pass flows on TT-1102"], ["Tube metal limit has two values on record"], ["THX-FH-manual-crude-charge-heater.pdf", "THX-SB-2026-06-tube-metal-limit.pdf"], None, None, None),
        ("shift_handover", None, "Shift handover: 3 open work orders, 1 alarm, 4 open conflicts", "Handover from Kiran Joshi to Meera Pillai on the CDU. Open: seal failure on P-1101A, vibration on K-2101A, bearing temperature on P-6101C. One permit is waiting for a second signature. Four knowledge conflicts are open.", "normal", 1, ["Chase the second signature on PTW-DEMO-0800", "Review the open conflicts"], [], [], None, None, None),
    ]
    for trigger, tag, headline, body, prio, age, actions, warns, files, ack, wo, cs in specs:
        brief(trigger, tag, headline, body, prio, age, actions, warns, files, ack=ack, requires_cs=trigger == "ptw",
              countersigned=cs, wo=None if trigger == "ptw" else wo, ptw=wo if trigger == "ptw" else None)
    # A permit that is acknowledged by someone else and waits for the demo user as second authority.
    sc.briefs[3]["acknowledged_by"] = PERSON["eng-1"].name
    sc.briefs[3]["acknowledged_at"] = None  # set only by a countersign, per the dual sign-off rule
    # More routine briefs, to fill the inbox and the push-volume history.
    routine = [
        ("work_order", ("P-1102B", "FV-1101", "E-1102", "P-6101A", "P-3101A", "XV-5102", "P-5101B", "PSV-2101")),
    ]
    for tag in routine[0][1]:
        a = by_tag[tag]
        age = rng.randint(12, 24 * 28)
        brief("work_order", tag, f"Work order on {tag}: {rng.choice(list(DESC.values()))}",
              f"A work order was raised on {a.name}. No recurring pattern in the last 90 days. The equipment manual and the latest inspection report are cited below.",
              rng.choice(("normal", "high")), age, ["Review the cited inspection report"], [],
              [f for f in ("INSP-P-1101A-seal-inspection.pdf", "HFS-CP-manual-crude-feed-pumps.pdf")],
              ack=PERSON[rng.choice(("shift-a", "shift-b"))].name if age > 24 else None, conf=round(rng.uniform(0.78, 0.93), 2))
    # Site-wide handover briefs, addressed to the showcase site so every showcase user sees them. A handover is
    # read at the next shift change, so only the last day's are still unacknowledged; the older ones were read.
    leads = ("shift-a", "shift-b", "shift-c")
    for i in range(14):
        age = rng.randint(2, 24 * 26)
        site = SITE_A if i % 4 else SITE_B
        wo, al = rng.randint(0, 4), rng.randint(0, 2)
        out_lead, in_lead = PERSON[leads[i % 3]].name, PERSON[leads[(i + 1) % 3]].name
        brief("shift_handover", None, f"Shift handover: {wo} open work orders, {al} alarms",
              f"Handover from {out_lead} to {in_lead} at the {SITE_NAME[site]}. {wo} open work order{'s' if wo != 1 else ''} and "
              f"{al} alarm{'s' if al != 1 else ''} carried over. Review open permits and conflicts before taking over.",
              "normal", age, ["Review open permits", "Read the previous shift log"], [], [],
              ack=in_lead if age > 12 else None, recipient=f"site-{site}", conf=0.9)
    for i in range(1, 8, 2):  # feedback on delivered briefs
        sc.brief_feedback.append({"id": _uid("feedback", sc.briefs[i]["brief_id"]), "brief_id": sc.briefs[i]["brief_id"], "rating": ("accurate", "accurate", "missing_context", "accurate")[i // 2],
                                  "notes": ("Spot on.", "Good, cited the right bulletin.", "Did not mention the spare pump being tagged out.", None)[i // 2],
                                  "submitted_by": PERSON["shift-a"].name, "submitted_at": _iso(anchor - timedelta(hours=rng.randint(1, 20)))})


def _knowledge_capture(sc: Showcase, by_tag, rng, anchor):
    qs = {
        "P-1101A": ["What was the barrier fluid pot level before the seal failed?", "How long had the pump run below minimum flow?", "Was the seal flush plan checked after the last overhaul?"],
        "K-2101A": ["Did the vibration trend change after the oil filter change?", "Where on the frame is the vibration highest?"],
        "P-3101B": ["Was the alignment checked hot after the overhaul?", "How does the bearing temperature compare with the sister pump?"],
        "FV-1103": ["How often is the valve stroked by hand?", "Did tightening the packing change the deadband?"],
        "P-6101C": ["Was the bearing replaced with the revision in the bulletin?", "What was the oil condition at the last sample?"],
    }
    for i, (tag, questions) in enumerate(qs.items()):
        a = by_tag[tag]
        completed = i in (1, 2)
        # The work order the questions are about: this asset's most recent closed one.
        closed = [e for e in sc.history_events if e["event_type"] == "work_order_created" and e["asset_id"] == a.asset_id
                  and e["payload"].get("close_notes")]
        sc.elicitation_sessions.append({
            "session_id": _uid("elicitation", tag), "work_order_id": closed[-1]["payload"]["work_order_id"],
            "asset_id": a.asset_id, "questions": questions, "status": "completed" if completed else "questions_ready",
            "triggered_by": PERSON["rel-1"].name, "created_at": _iso(anchor - timedelta(days=9 - i)),
            "updated_at": _iso(anchor - timedelta(days=8 - i)),
        })
    # Three retiring experts, each with a programme of interview sessions in different states.
    plans = [
        (EXPERTS[0], 6, 3, 7, ("PUMP", "SEAL", "COMPRESSOR", "INSTRUMENT", "HEAT EXCHANGER", "VALVE")),
        (EXPERTS[1], 5, 1, 10, ("HEATER", "HEAT EXCHANGER", "VESSEL", "VALVE", "PUMP")),
        (EXPERTS[2], 5, 0, 12, ("COMPRESSOR", "INSTRUMENT", "CONTROL VALVE", "TRANSMITTER", "PUMP")),
    ]
    for idx, ((pid, name, email, area), total, done, interval, families) in enumerate(plans):
        sid = _uid("offboarding", pid)
        first = anchor - timedelta(days=interval * done + 2)
        sc.offboarding_sessions.append({
            "id": sid, "personnel_id": pid, "personnel_email": email,
            "retirement_date": (anchor + timedelta(days=45 + 20 * idx)).date().isoformat(),
            "total_sessions": total, "session_interval_days": interval,
            "status": "in_progress" if done else "scheduled", "created_by": PERSON["rel-1"].name,
            "created_at": _iso(first - timedelta(days=1)),
        })
        for n in range(total):
            state = "completed" if n < done else ("questions_ready" if n == done else "pending")
            fam = families[n]
            sc.offboarding_items.append({
                "id": _uid("offboarding-item", pid, str(n)), "session_id": sid, "session_number": n + 1,
                "equipment_family": fam, "focus_failure_modes": [],
                "status": state,
                "questions": ([f"Which {fam.lower()} assets in the plant are the most sensitive to operating outside their design window, and how do you tell?",
                               f"What did you learn about {fam.lower()} failures that is not written down anywhere?",
                               f"Which recurring {fam.lower()} problem would you hand over first, and why?"] if state != "pending" else []),
                "scheduled_for": _iso(first + timedelta(days=interval * n)),
                "completed_at": _iso(first + timedelta(days=interval * n, hours=2)) if state == "completed" else None,
            })


def unmarked(sc: Showcase) -> list[tuple[str, dict]]:
    """Every direct-insert row that carries no showcase marker. Empty is the only acceptable answer:
    a row without a marker would be real data as far as a real account is concerned."""
    bad: list[tuple[str, dict]] = []
    for table, rows in sc.tables().items():
        for row in rows:
            if table in ("operational_events", "plant_operating_states"):
                ok = is_demo_site(row.get("site_id"))
            elif table == "offboarding_sessions":
                ok = is_demo_id(row.get("personnel_id"))
            elif table == "offboarding_session_items":
                ok = True  # hangs off a showcase session; checked through its parent
            elif table == "brief_feedback":
                ok = True  # hangs off a showcase brief; checked through its parent
            elif table == "asset_alias_map":
                ok = is_demo_id(row.get("canonical_asset_id"))
            elif table == "briefs":
                ok = is_demo_id(row.get("asset_id"))
            else:
                ok = is_demo_id(row.get("asset_id"))
            if not ok:
                bad.append((table, row))
    return bad
