"""The showcase document set: about 70 hand-written manuals, bulletins, procedures, inspection reports,
regulatory summaries, permits and shift logs, plus three generated records for every piece of equipment
(datasheet, test record, maintenance history card), written as the plant's own paperwork.

Each document names the equipment it is about by tag, because that is what the ingestion pipeline
links on (a confirmed alias per tag is loaded with the assets). Specific numbers (set pressures,
intervals, part numbers) are stated exactly once per source so the Copilot has a fact to cite, and
ten of them are stated twice with different values, by a procedure and by a later bulletin: those are
the knowledge conflicts the governance pages show.

Nothing here is copied from the golden dataset (see `spec.py`).
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from scripts.showcase.spec import (
    COLUMN,
    COMPRESSOR,
    CONTROL_VALVE,
    EXCHANGER,
    HEATER,
    HP_PUMP,
    ISOLATION_VALVE,
    LOADING,
    PERSON,
    PLANT_NAME,
    PUMP,
    RELIEF,
    SITE_NAME,
    TANK,
    TRANSMITTER,
    UNIT,
    VESSEL,
    Asset,
)

OEM = {
    "pump": ("Halden Fluid Systems", "HFS"),
    "hp_pump": ("Halden Fluid Systems", "HFS"),
    "compressor": ("Norwick Compression", "NWC"),
    "heater": ("Thermex Combustion", "THX"),
    "exchanger": ("Karvel Heat Transfer", "KHT"),
    "relief": ("Sentinel Valve Works", "SVW"),
    "control_valve": ("Calder Controls", "CLC"),
    "tank": ("Orbis Tank Systems", "OTS"),
    "loading": ("Marlow Loading Systems", "MLS"),
    "instrument": ("Calder Controls", "CLC"),
}


def _oem_key(equipment_class: str) -> str:
    """The `OEM` table key for an asset class."""
    return {PUMP: "pump", HP_PUMP: "hp_pump", COMPRESSOR: "compressor", HEATER: "heater", EXCHANGER: "exchanger",
            RELIEF: "relief", CONTROL_VALVE: "control_valve", ISOLATION_VALVE: "control_valve", TANK: "tank",
            LOADING: "loading", TRANSMITTER: "instrument"}.get(equipment_class, "")


@dataclass(frozen=True)
class Conflict:
    """A parameter two sources disagree on. The procedure (older, authority 4) states `old`; the
    bulletin (newer, authority 3) states `new`."""

    key: str
    asset_tag: str
    parameter: str
    unit: str
    old: str
    new: str
    track: str
    severity: str
    status: str
    sop_file: str
    bulletin_file: str


CONFLICTS: tuple[Conflict, ...] = (
    Conflict("c01", "PSV-1101", "set_pressure", "barg", "18.0", "16.8", "engineering", "major", "pending_moc",
             "SOP-CDU-PSV-test-and-reset.pdf", "SVW-SB-2026-07-psv-set-pressure.pdf"),
    Conflict("c02", "P-1101A", "minimum_continuous_flow", "m3/h", "120", "150", "engineering", "major", "pending_moc",
             "SOP-CDU-crude-feed-pump-operation.pdf", "HFS-SB-2026-05-minimum-flow.pdf"),
    Conflict("c03", "K-2101A", "discharge_temperature_trip", "degC", "135", "125", "engineering", "major", "open",
             "SOP-HDT-recycle-compressor-start.pdf", "NWC-SB-2026-09-discharge-temperature.pdf"),
    Conflict("c04", "H-1101", "tube_metal_temperature_limit", "degC", "620", "595", "engineering", "major", "open",
             "SOP-CDU-heater-light-off.pdf", "THX-SB-2026-06-tube-metal-limit.pdf"),
    Conflict("c05", "T-6101", "maximum_fill_level", "percent", "92", "88", "engineering", "major", "pending_moc",
             "SOP-TKF-tank-filling-limits.pdf", "OTS-SB-2026-08-fill-level.pdf"),
    Conflict("c06", "XV-1102", "stroke_test_interval", "months", "12", "6", "administrative", "minor", "open",
             "SOP-CDU-ESD-valve-testing.pdf", "SVW-SB-2026-04-esd-valve-test-interval.pdf"),
    Conflict("c07", "P-3101A", "bearing_temperature_alarm", "degC", "85", "80", "administrative", "minor", "resolved",
             "SOP-UTL-cooling-water-pump-operation.pdf", "HFS-SB-2026-02-bearing-temperature.pdf"),
    Conflict("c08", "E-1101", "cleaning_interval", "months", "24", "18", "administrative", "minor", "resolved",
             "SOP-CDU-preheat-train-cleaning.pdf", "KHT-SB-2026-03-cleaning-interval.pdf"),
    Conflict("c09", "V-2101", "corrosion_allowance", "mm", "3.0", "2.5", "engineering", "major", "resolved",
             "SOP-HDT-separator-inspection-plan.pdf", "OEM-V-2101-design-revision.pdf"),
    Conflict("c10", "LA-6101", "maximum_loading_rate", "m3/h", "180", "150", "administrative", "minor", "open",
             "SOP-TKF-truck-loading.pdf", "MLS-SB-2026-10-loading-rate.pdf"),
)
CONFLICT_BY_TAG = {c.asset_tag: c for c in CONFLICTS}

# Failure families that recur on purpose (tag, failure codes, days ago per occurrence). The work orders
# are raised from this (history.py) and each asset's maintenance history card is written from it, so the
# paperwork and the event feed tell the same story.
CHAINS = (
    ("P-1101A", ("SEAL-FAIL", "LEAK-MECH"), (84, 63, 41, 19)),
    ("P-3101B", ("BEARING-FAIL", "VIBE-HIGH", "MISALIGN"), (77, 52, 26)),
    ("K-2101A", ("VIBE-HIGH",), (70, 45, 22)),
    ("P-2101B", ("SEAL-FAIL", "LEAK-MECH"), (66, 35)),
    ("FV-1103", ("STICTION",), (58, 33, 9)),
    ("P-6101C", ("BEARING-FAIL", "VIBE-HIGH", "MISALIGN"), (60, 31)),
    ("E-1107B", ("HIGH-TEMP",), (74, 40)),
    ("P-1102A", ("SEAL-FAIL", "LEAK-MECH"), (50, 17)),
)
CHAIN_BY_TAG = {c[0]: c for c in CHAINS}

DESC = {
    "SEAL-FAIL": "Mechanical seal leaking at the gland, product visible on the baseplate",
    "LEAK-MECH": "Seal flush line weeping, barrier fluid level dropping",
    "BEARING-FAIL": "Drive end bearing running hot, temperature trending up over the shift",
    "VIBE-HIGH": "Vibration alarm on the drive end, reading above the alarm setpoint",
    "MISALIGN": "Coupling guard noise, suspected misalignment after the last overhaul",
    "LOW-FLOW": "Discharge flow below the minimum continuous flow, recirculation valve hunting",
    "HIGH-TEMP": "Outlet temperature above the control band, firing reduced",
    "PRESSURE-LOSS": "Discharge pressure falling with no change in demand",
    "DRIFT-CAL": "Transmitter reading drifts against the local gauge, calibration required",
    "STICTION": "Valve sticks on small moves, controller output cycling",
    "ACTUATOR": "Actuator slow to close on the test stroke",
    "NOISE-ABN": "Abnormal noise heard during the walk-round",
}



@dataclass(frozen=True)
class Doc:
    file_name: str
    document_type: str  # one of routers/documents.py DOCUMENT_TYPES
    authority: int
    asset_id: str
    title: str
    text: str
    mime: str = "application/pdf"
    age_days: int = 60  # how long before the anchor the document was issued


def _hdr(no: str, rev: str, title: str, owner: str, issued: datetime, site: str) -> str:
    return (
        f"{PLANT_NAME}\n{SITE_NAME[site]}\n\nDocument no: {no}   Revision: {rev}\n"
        f"Title: {title}\nOwner: {owner}\nIssued: {issued:%d %B %Y}\n\n"
    )


# --- Per-asset records -------------------------------------------------------------------------
# The graph links an asset to its knowledge only through documents, so an asset with none shows an empty
# Knowledge tab and graph. Every piece of equipment therefore gets three records: a datasheet (OEM data,
# authority 3), a test record (authority 4) and a maintenance history card (authority 5), written from its
# class. They state nothing a manual or bulletin states and nothing that could contradict one (no
# operating limits, intervals or fill levels): an asset in `CONFLICTS` is left to its own documents.

RECORDS_PER_ASSET = 3
# Written out, and model codes without a number: a string shaped like a tag but naming no equipment ("HFS-843",
# "PID-CDU-06") is extracted as an unresolved asset tag and queued for review, and a record would queue one each.
_SHEETS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_MECH, _INSTR, _ELEC = ("tech-1", "tech-2"), ("tech-3",), ("tech-4",)


def _pump(r: random.Random, hp: bool = False) -> tuple[list[str], tuple[str, list[str]], list[str], tuple]:
    kw = r.choice([160, 250, 400, 630] if hp else [7.5, 11, 15, 22, 30, 37, 55, 75, 110, 160])
    return (
        [f"Driver: electric motor, {kw} kW, {r.choice([1480, 2970])} rpm.",
         f"Casing: {'barrel, forged steel' if hp else 'carbon steel, API 610 type OH2'}.",
         f"Seal: {r.choice(['single', 'double'])} mechanical seal, flush plan {r.choice(['11', '32', '53B'])}.",
         "Coupling: spacer type with guard."],
        ("Condition and performance test",
         [f"Vibration at the drive end bearing {r.uniform(1.1, 3.4):.1f} mm/s RMS.",
          f"Bearing temperature {r.randint(48, 72)} degC at steady load.", "Seal leakage: none visible.",
          "Discharge pressure and motor current within the commissioning curve."]),
        ["Oil change and bearing inspection", "Coupling alignment check", "Seal flush line inspection"], _MECH)


def _compressor(r: random.Random) -> tuple:
    return (
        [f"Two-stage reciprocating compressor, {r.choice([450, 750, 1100])} kW driver.",
         f"Cylinders: {r.choice(['two', 'four'])}, lubricated, water cooled.", "Valves: plate type, per cylinder."],
        ("Condition test", [f"Frame vibration {r.uniform(4.0, 8.0):.1f} mm/s RMS.",
                            f"Cylinder discharge temperature {r.randint(92, 112)} degC.", "Lube oil pressure steady.",
                            "Rod drop within the packing records."]),
        ["Valve inspection", "Packing check", "Cooler cleaning"], _MECH)


def _vessel(r: random.Random, kind: str) -> tuple:
    return (
        ["Design code: ASME VIII Division 1.", f"Shell material: SA-516 grade 70, {r.choice([12, 16, 20, 25])} mm nominal.",
         f"{kind}: insulated, with a nameplate and a stamped registration number."],
        ("External inspection and thickness survey",
         [f"Minimum measured wall {r.uniform(10.5, 22.0):.1f} mm at the survey points.",
          "No active leaks, coating in sound condition.", "Supports, nozzles and platforms examined."]),
        ["External visual inspection", "Insulation check", "Nozzle and flange check"], _MECH)


_CLASS_RECORDS = {
    PUMP: lambda r: _pump(r),
    HP_PUMP: lambda r: _pump(r, hp=True),
    COMPRESSOR: _compressor,
    VESSEL: lambda r: _vessel(r, "Pressure vessel"),
    COLUMN: lambda r: _vessel(r, "Column"),
    EXCHANGER: lambda r: (
        ["Type: shell and tube, TEMA AES.", f"Tube bundle: {r.choice([180, 240, 320])} tubes, carbon steel.",
         "Shell side: hydrocarbon; tube side: process fluid."],
        ("Tube bundle inspection", [f"Plugged tubes: {r.randint(0, 4)}.", "Eddy current survey completed on the bundle.",
                                    "Tubesheet and gaskets in sound condition."]),
        ["Bundle pull and cleaning check", "Gasket replacement", "Insulation check"], _MECH),
    HEATER: lambda r: (
        [f"Fired heater, {r.choice([4, 6, 9])} MW design duty.", f"Burners: {r.choice([4, 6, 8])}, forced draught.",
         "Tubes: chrome-moly, vertical, radiant and convection sections."],
        ("Burner and tube inspection", ["Burner tips cleaned and flames stable.", "Tube thermography completed, no hot spots.",
                                        "Refractory in sound condition."]),
        ["Burner inspection", "Tube inspection", "Refractory check"], _MECH),
    CONTROL_VALVE: lambda r: (
        [f"Globe control valve, {r.choice(['DN50', 'DN80', 'DN100', 'DN150'])}, equal percentage trim.",
         f"Actuator: pneumatic diaphragm, fail {r.choice(['open', 'closed'])}.", "Positioner: smart, HART."],
        ("Stroke and positioner calibration",
         [f"Hysteresis {r.uniform(0.1, 0.6):.2f} percent of span.", "Full stroke travel confirmed at 0, 50 and 100 percent.",
          "Positioner re-tuned and a signature recorded."]),
        ["Positioner calibration", "Packing adjustment", "Air supply filter change"], _INSTR),
    ISOLATION_VALVE: lambda r: (
        [f"{r.choice(['Ball', 'Gate'])} valve, {r.choice(['DN80', 'DN100', 'DN150', 'DN200'])}, class 300.",
         "Actuator: pneumatic spring return, fail closed.", "Fire safe design; position indicated at the valve."],
        ("Stroke test", [f"Closure time {r.uniform(3.5, 6.8):.1f} seconds.", "Seat test passed, no visible leakage.",
                         "Limit switches and solenoid confirmed."]),
        ["Stroke test", "Actuator inspection", "Solenoid check"], _INSTR),
    RELIEF: lambda r: (
        [f"Set pressure {r.choice([6.5, 9.0, 12.5, 21.0, 34.0])} barg, orifice {r.choice(['F', 'H', 'J', 'K'])}.",
         "Spring loaded, conventional, flanged.", "Discharges to the flare header."],
        ("Bench test and reset", ["Popped within tolerance of the set pressure on the third lift.", "Seat tight after reset.",
                                  "Seal wire and tag renewed."]),
        ["Bench test", "Inlet and outlet line inspection", "Tag check"], _INSTR),
    TRANSMITTER: lambda r: (
        [f"Smart transmitter, 4 to 20 mA with HART, range {r.choice(['0 to 10', '0 to 40', '0 to 100', '0 to 250'])} "
         f"{r.choice(['barg', 'degC', 'percent', 'm3/h'])}.", "Diaphragm: stainless steel; enclosure rated for the area.",
         "Loop checked from the field to the control system."],
        ("Calibration record", [f"As-found error {r.uniform(0.05, 0.25):.2f} percent of span.",
                                f"As-left error {r.uniform(0.01, 0.06):.2f} percent of span.", "Loop check and tag confirmed."]),
        ["Calibration", "Impulse line check", "Junction box inspection"], _INSTR),
    TANK: lambda r: (
        [f"Fixed cone roof tank, capacity {r.choice([5000, 10000, 15000, 20000])} m3.", "Shell: carbon steel with a floor lining.",
         "Equipped with a vent relief valve, radar gauge and a foam line."],
        ("External inspection", ["Shell settlement within the survey tolerance.", "Radar gauge checked against a manual dip.",
                                 "Vent relief valve and flame arrestor examined."]),
        ["Gauge check", "Shell and roof inspection", "Foam line check"], _MECH),
    LOADING: lambda r: (
        ["Top loading arm with a vapour recovery connection.", "Swivel joints and counterbalance spring assembly.",
         "Earthing monitor and overfill probe interlock fitted."],
        ("Inspection and function test", ["Swivel joints free, no seep from the seals.", "Earthing monitor and overfill probe tested.",
                                          "Counterbalance within the arm travel."]),
        ["Swivel joint inspection", "Hose and coupling check", "Interlock function test"], _MECH),
}
_DEFAULT_RECORD = lambda r: (  # noqa: E731 - any other class (the cooling tower)
    ["Packaged equipment, installed and commissioned by the supplier.", "Details are in the supplier file.",
     "Nameplate fitted and registered."],
    ("Condition test", ["Vibration and temperature readings recorded within the commissioning values.", "Visual check complete."]),
    ["General inspection", "Lubrication", "Fastener check"], _MECH)


def build_documents(assets: list[Asset], anchor: datetime) -> list[Doc]:
    by_tag = {a.tag: a for a in assets}

    def a(tag: str) -> Asset:
        return by_tag[tag]

    def issued(days: int) -> datetime:
        return anchor - timedelta(days=days)

    docs: list[Doc] = []

    def add(file_name, dtype, authority, tag, title, body, days=60, mime="application/pdf", no=None, rev="A", owner=None):
        asset = a(tag)
        header = _hdr(no or file_name.rsplit(".", 1)[0].upper(), rev, title, owner or PERSON["rel-1"].name,
                      issued(days), asset.site_id)
        header += f"Primary equipment: {asset.tag}, {asset.name}\n\n"
        docs.append(Doc(file_name, dtype, authority, asset.asset_id, title, header + body, mime, days))

    # --- OEM manuals (authority 3) ------------------------------------------------------------
    add("HFS-CP-manual-crude-feed-pumps.pdf", "oem_manual", 3, "P-1101A",
        "Operation and maintenance manual, HFS-CP 150-315 centrifugal pump",
        "Applies to pumps P-1101A and P-1101B (crude feed), P-1102A and P-1102B (reflux) and P-1103A "
        "and P-1103B (bottoms).\n\nDesign data. Design pressure 24 barg, design temperature 360 degC, rated flow 310 m3/h, "
        "rated head 148 m. Mechanical seal HAL-MS-4471 revision B, double seal with API Plan 53B barrier "
        "fluid at 2.5 bar above process pressure.\n\nLubrication. Bearing housings use ISO VG 68 oil; change "
        "oil every 4,000 operating hours. Bearing temperature alarm 85 degC, trip 95 degC.\n\nMinimum "
        "continuous flow is 120 m3/h. Operation below this causes recirculation and seal face damage.\n\n"
        "Seal inspection interval 8,000 operating hours. Alignment tolerance 0.05 mm total indicator reading.\n",
        days=900, no="HFS-CP-150-315-OM", rev="C")
    add("HFS-HP-manual-reactor-charge-pumps.pdf", "oem_manual", 3, "P-2101A",
        "Operation manual, HFS-HP 40-12 reactor charge pump",
        "Applies to reactor charge pumps P-2101A and P-2101B (HDT). Design pressure 112 barg, design "
        "temperature 250 degC, rated flow 95 m3/h. Barrel casing, tandem mechanical seal HAL-MS-5810. "
        "Warm-up rate must not exceed 50 degC per hour. Minimum continuous flow 40 m3/h. Vibration alarm "
        "4.5 mm/s RMS, trip 7.1 mm/s RMS at the drive end bearing.\n", days=1100, no="HFS-HP-40-12-OM", rev="B")
    add("NWC-RC-manual-recycle-gas-compressors.pdf", "oem_manual", 3, "K-2101A",
        "Operation manual, NWC-H4 reciprocating recycle gas compressor",
        "Applies to K-2101A and K-2101B. Two-stage reciprocating compressor, discharge pressure 95 barg, "
        "hydrogen service. Cylinder discharge temperature alarm 120 degC and trip 130 degC. Rod load limit "
        "180 kN. Frame vibration alarm 12 mm/s, trip 18 mm/s. Valve inspection interval 4,000 hours; "
        "packing replacement interval 16,000 hours. Lube oil pressure low alarm 2.0 bar.\n",
        days=1300, no="NWC-H4-OM", rev="D")
    add("THX-FH-manual-crude-charge-heater.pdf", "oem_manual", 3, "H-1101",
        "Operation and maintenance manual, THX-FH4 fired heater",
        "Applies to H-1101 (crude charge heater). Duty 38 MW, four passes, radiant tubes in 9Cr-1Mo "
        "alloy. Design tube metal temperature 650 degC. Burner management system requires a purge of five "
        "furnace volumes before light-off. Flame failure shuts the fuel gas valve within 3 seconds. Pass "
        "flow low trip 70 percent of design. Stack oxygen target 2.5 to 3.5 percent.\n", days=1500, no="THX-FH4-OM", rev="B")
    add("SVW-PSV-manual-pressure-safety-valves.pdf", "oem_manual", 3, "PSV-1101",
        "Maintenance manual, SVW-9 series pressure safety valves",
        "Applies to PSV-1101 to PSV-1104 (CDU), PSV-2101 to PSV-2103 (HDT), PSV-3101 and PSV-3102 (steam "
        "drum) and PSV-4101 (flare header). Spring-loaded, balanced bellows. Set pressure tolerance plus or "
        "minus 3 percent. Bench test and reset every 24 months; stroke test of the lifting lever "
        "annually. Blowdown 7 percent.\n", days=1200, no="SVW-9-MM", rev="C")
    add("KHT-ST-manual-shell-tube-exchangers.pdf", "oem_manual", 3, "E-1101",
        "Maintenance manual, KHT-STX shell and tube exchangers",
        "Applies to the crude preheat train E-1101 to E-1106, overhead condensers E-1107A to E-1107D "
        "and the HDT feed effluent exchangers E-2101 to E-2105. Fixed tubesheet with expansion joint, "
        "carbon steel shell, tubes in 304L. Hydrotest at 1.3 times design pressure. Recommended cleaning "
        "interval 24 months, shortened where the fouling factor exceeds 0.0006 m2K/W.\n", days=1400, no="KHT-STX-MM", rev="B")
    add("CLC-CV-manual-control-valves.pdf", "oem_manual", 3, "FV-1101",
        "Installation and maintenance manual, CLC-GL control valves",
        "Applies to control valves FV-1101 to FV-1106 and FV-2101 to FV-2104. Globe body, pneumatic "
        "actuator, digital positioner. Full stroke time 6 seconds. Deadband should not exceed 1 percent "
        "of span; a deadband above 2 percent indicates stiction and calls for packing replacement. "
        "Positioner calibration every 12 months.\n", days=800, no="CLC-GL-MM", rev="A")
    add("OTS-TK-manual-storage-tanks.pdf", "oem_manual", 3, "T-6101",
        "Design and operating manual, OTS fixed-roof storage tanks",
        "Applies to tanks T-6101 to T-6108. Capacity 12,500 m3 each, carbon steel, fixed roof with "
        "internal floating pan. Design level 14.2 m. Maximum normal fill level 92 percent of shell height; high-high level "
        "alarm at 95 percent. Overfill protection by independent radar gauge. Annual external inspection; "
        "internal inspection every 10 years.\n", days=2000, no="OTS-TK-DOM", rev="B")
    add("HFS-FW-manual-fire-water-pumps.pdf", "oem_manual", 3, "P-6201A",
        "Operation manual, HFS-FW diesel-driven fire water pump",
        "Applies to P-6201A, P-6201B and P-6201C. Rated flow 410 m3/h at 10.5 barg. Diesel engine starts "
        "on fire main pressure below 7.0 barg; weekly test run of 30 minutes at rated speed. Battery "
        "banks to be replaced every 3 years. Fuel tank to be kept above 80 percent.\n", days=1000, no="HFS-FW-OM", rev="A")
    add("MLS-LA-manual-loading-arms.pdf", "oem_manual", 3, "LA-6101",
        "Operation manual, MLS-TL top-loading arms",
        "Applies to LA-6101 to LA-6103 (tank farm) and LA-5101 to LA-5104 (blending and dispatch). "
        "Earthing check required before connection. Swing joint inspection every 12 months; grounding "
        "continuity test every 6 months. Vapour return interlock must be proven before loading starts.\n",
        days=950, no="MLS-TL-OM", rev="A")

    # --- Conflicting pairs: older procedure (authority 4) and newer bulletin (authority 3) -------
    sop_topics = {
        "c01": ("pressure safety valve PSV-1101 on the atmospheric column C-1101", "Bench test and reset PSV-1101 at a set pressure of {old} {unit}. After reset record the lift pressure and the reseat pressure."),
        "c02": ("crude feed pump P-1101A", "Never run P-1101A below the minimum continuous flow of {old} {unit}. If the flow falls below it open the minimum flow bypass."),
        "c03": ("recycle gas compressor K-2101A", "Trip K-2101A when the discharge temperature reaches {old} {unit}. Do not restart until the cylinder cooling is checked."),
        "c04": ("crude charge heater H-1101", "Keep the tube metal temperature of H-1101 below {old} {unit}. Reduce firing if any skin thermocouple exceeds the limit."),
        "c05": ("storage tank T-6101", "Stop filling tank T-6101 at a maximum fill level of {old} {unit}. Confirm the radar gauge against the manual dip."),
        "c06": ("emergency isolation valve XV-1102", "Stroke test XV-1102 every {old} {unit} and record the closure time against the 8 second limit."),
        "c07": ("cooling water pump P-3101A", "Raise a work order if the bearing temperature of P-3101A exceeds {old} {unit}."),
        "c08": ("crude preheat exchanger E-1101", "Schedule cleaning of E-1101 every {old} {unit} or when the heat transfer duty drops 15 percent."),
        "c09": ("hot high pressure separator V-2101", "The inspection plan assumes a corrosion allowance of {old} {unit} for vessel V-2101 when calculating remaining life."),
        "c10": ("truck loading arm LA-6101", "Limit the loading rate on LA-6101 to {old} {unit} until the vapour return line is proven open."),
    }
    for c in CONFLICTS:
        asset = a(c.asset_tag)
        topic, rule = sop_topics[c.key]
        add(c.sop_file, "procedure", 4, c.asset_tag, f"Operating procedure: {topic}",
            f"Purpose. This procedure covers the {topic}.\n\nRequirement. " + rule.format(old=c.old, unit=c.unit) +
            f"\n\nResponsibility. The shift lead of the {asset.unit} unit is responsible for compliance with this "
            "procedure; deviations are reported to the process engineer.\n", days=420 + 17 * int(c.key[1:]),
            rev="C", owner=PERSON["eng-1"].name)
        oem_key = ("relief" if "PSV" in c.asset_tag else "compressor" if c.asset_tag.startswith("K") else
                   "heater" if c.asset_tag.startswith("H") else "exchanger" if c.asset_tag.startswith("E") else
                   "tank" if c.asset_tag.startswith("T") else "loading" if c.asset_tag.startswith("LA") else
                   "control_valve" if c.asset_tag.startswith("XV") else "pump")
        maker, code = OEM["pump"] if c.asset_tag.startswith("P") else OEM[oem_key]
        add(c.bulletin_file, "oem_manual", 3, c.asset_tag, f"{maker} service bulletin: {c.parameter.replace('_', ' ')} for {c.asset_tag}",
            f"Service bulletin {code}-SB-2026 revision A, issued by {maker}.\n\nSubject. Revision of the {c.parameter.replace('_', ' ')} "
            f"for {c.asset_tag}.\n\nThe previously published value of {c.old} {c.unit} is withdrawn. The {c.parameter.replace('_', ' ')} "
            f"for {c.asset_tag} is now {c.new} {c.unit}. Operators must update site procedures and records that quote the old "
            f"value. This bulletin supersedes the value in the operation manual.\n", days=90 - 6 * int(c.key[1:]),
            rev="A", owner=maker)

    # --- More procedures (authority 4) -------------------------------------------------------
    sops = [
        ("SOP-CDU-startup-sequence.pdf", "P-1101A", "Start-up of the crude distillation unit",
         "Confirm the heater purge, line up crude feed through P-1101A or P-1101B, establish reflux with P-1102A "
         "and bring the column to temperature at 30 degC per hour. Do not exceed the heater outlet temperature "
         "of 365 degC during heat-up. Hand over the unit to the shift lead only when the column pressure is steady "
         "at 1.4 barg.", PERSON["eng-1"]),
        ("SOP-CDU-shutdown-sequence.pdf", "P-1101A", "Normal shutdown of the crude distillation unit",
         "Reduce charge rate to 60 percent, cool the heater at 40 degC per hour, stop P-1101A last. Drain the "
         "desalter V-1101 interface before isolation. The shift lead signs the shutdown log.", PERSON["eng-1"]),
        ("SOP-CDU-pump-changeover.pdf", "P-1101B", "Changeover of crude feed pumps P-1101A and P-1101B",
         "Start the standby pump P-1101B, confirm discharge pressure and flow, then stop P-1101A slowly closing "
         "its discharge valve. Check the seal barrier pressure on the pump that has stopped. Changeover must be "
         "logged in the shift log.", PERSON["shift-a"]),
        ("SOP-CDU-isolation-and-lockout.pdf", "XV-1101", "Isolation and lockout for CDU pumps",
         "Isolate pumps P-1101A, P-1101B, P-1102A and P-1102B by closing the suction and discharge valves, "
         "locking out the motor breaker and draining the casing. Two people verify the isolation before a permit "
         "to work is issued. Emergency isolation valves XV-1101 to XV-1104 are tested separately.", PERSON["hse-1"]),
        ("SOP-HDT-reactor-startup.pdf", "R-2101", "Start-up of the hydrotreating reactor R-2101",
         "Dry out the reactor with nitrogen, sulphide the catalyst at the rate of 25 degC per hour and hold bed 1 "
         "and bed 2 temperatures within 10 degC of each other. Hydrogen purity must be above 85 percent before "
         "feed is introduced. Never exceed a reactor inlet pressure of 98 barg.", PERSON["eng-2"]),
        ("SOP-HDT-charge-pump-operation.pdf", "P-2101A", "Operation of reactor charge pumps P-2101A and P-2101B",
         "Warm the pump casing at no more than 50 degC per hour. Start only against a minimum flow line open. "
         "Check the tandem seal pot level every shift. A vibration above 4.5 mm/s requires a work order.", PERSON["eng-2"]),
        ("SOP-HDT-compressor-changeover.pdf", "K-2101B", "Changeover of recycle gas compressors K-2101A and K-2101B",
         "Load K-2101B in steps of 25 percent while unloading K-2101A. Confirm lube oil pressure above 2.0 bar and "
         "frame vibration below 12 mm/s on the running machine.", PERSON["eng-2"]),
        ("SOP-UTL-cooling-water-changeover.pdf", "P-3101B", "Cooling water pump changeover",
         "Three cooling water pumps P-3101A, P-3101B and P-3101C serve the plant; two run and one is standby. "
         "Rotate the standby every month. Record header pressure before and after.", PERSON["shift-b"]),
        ("SOP-TKF-tank-gauging.pdf", "T-6102", "Tank gauging and dip checks",
         "Check the radar level gauge of each tank against a manual dip once per week. A difference above 20 mm "
         "is reported to the instrument technician. Record tank temperature with the level.", PERSON["shift-c"]),
        ("SOP-TKF-fire-water-testing.pdf", "P-6201B", "Weekly fire water pump test",
         "Run each diesel-driven fire water pump P-6201A, P-6201B and P-6201C for 30 minutes at rated speed every "
         "week. Record the discharge pressure, the engine oil pressure and the fuel level.", PERSON["hse-1"]),
        ("SOP-FLR-knockout-drum-draining.pdf", "V-4101", "Draining the flare knock-out drum V-4101",
         "Start the knock-out drum pump P-4101A when the level exceeds 40 percent. Never allow the level to reach "
         "70 percent. The seal drum V-4102 water seal is checked daily.", PERSON["shift-a"]),
        ("SOP-BLD-loading-arm-operation.pdf", "LA-5101", "Operation of loading arms LA-5101 to LA-5104",
         "Verify earthing, connect the vapour return line and prove the interlock before opening the dispatch "
         "isolation valves XV-5101 to XV-5104. Stop loading at the preset volume.", PERSON["shift-b"]),
    ]
    for i, (fn, tag, title, body, owner) in enumerate(sops):
        add(fn, "procedure", 4, tag, title, f"Purpose. {title}.\n\nMethod. {body}\n", days=300 + 23 * i, rev="B", owner=owner.name)

    # --- Inspection reports (authority 4) ----------------------------------------------------
    inspections = [
        ("INSP-C-1101-thickness-survey.pdf", "C-1101", "Thickness survey of atmospheric column C-1101",
         "Ultrasonic thickness readings at 48 locations. Minimum measured wall 14.2 mm against a retirement thickness "
         "of 11.5 mm. Corrosion rate 0.18 mm per year at the overhead section, remaining life 15 years. Result: satisfactory.", 150),
        ("INSP-H-1101-tube-survey.pdf", "H-1101", "Radiant tube survey of fired heater H-1101",
         "Eight tubes show creep bulging below 2 percent. Tube skin thermocouples TT-1102 indicates a hottest tube at "
         "588 degC. Two tubes on pass 3 flagged for replacement at the next turnaround. Result: conditional.", 110),
        ("INSP-V-2101-internal-inspection.pdf", "V-2101", "Internal inspection of hot high pressure separator V-2101",
         "Weld seams examined by magnetic particle testing; no linear indications. General corrosion 0.9 mm since last "
         "inspection. Demister pad replaced. Result: satisfactory.", 95),
        ("INSP-R-2101-reactor-shell.pdf", "R-2101", "Shell examination of hydrotreating reactor R-2101",
         "Hydrogen attack assessment found no fissuring. Skirt weld inspected by time of flight diffraction; "
         "no reportable defects. Result: satisfactory.", 130),
        ("INSP-PSV-1101-bench-test.pdf", "PSV-1101", "Bench test record, pressure safety valve PSV-1101",
         "As-found lift pressure 17.6 barg against a set pressure of 18.0 barg, within the 3 percent tolerance. "
         "Valve reset and sealed. Next bench test due in 24 months. Result: passed.", 200),
        ("INSP-PSV-1102-bench-test.pdf", "PSV-1102", "Bench test record, pressure safety valve PSV-1102",
         "As-found lift pressure 19.4 barg against a set pressure of 18.0 barg, outside tolerance. Seat lapped and "
         "retested at 18.1 barg. Result: failed as found, passed after repair.", 75),
        ("INSP-PSV-2101-bench-test.pdf", "PSV-2101", "Bench test record, pressure safety valve PSV-2101",
         "As-found lift 101.5 barg, set pressure 100.0 barg, within tolerance. Result: passed.", 180),
        ("INSP-PSV-3101-bench-test.pdf", "PSV-3101", "Bench test record, steam drum relief valve PSV-3101",
         "As-found lift 41.2 barg, set pressure 40.0 barg, within tolerance. Reset and sealed. Result: passed.", 160),
        ("INSP-E-1107A-tube-bundle.pdf", "E-1107A", "Tube bundle inspection, overhead condenser E-1107A",
         "Eddy current testing of 312 tubes found 9 with wall loss above 40 percent; all plugged. Fouling factor "
         "0.0007 m2K/W. Result: conditional, cleaning recommended.", 120),
        ("INSP-T-6101-external-inspection.pdf", "T-6101", "Annual external inspection of tank T-6101",
         "Shell settlement within 25 mm limit. Radar gauge reads within 8 mm of the manual dip. Vent relief valve "
         "PSV-6101 tagged and in date. Result: satisfactory.", 60),
        ("INSP-T-6102-floor-survey.pdf", "T-6102", "Floor survey of tank T-6102",
         "Floor plate loss up to 1.6 mm near the sump. Coating breakdown on 12 percent of the floor area. Result: "
         "conditional, recoat at the next outage.", 100),
        ("INSP-K-2101A-valve-inspection.pdf", "K-2101A", "Valve inspection, recycle gas compressor K-2101A",
         "Second stage discharge valve plates showed light wear. Rod load readings 162 kN. Packing leakage within "
         "limits. Result: satisfactory, next valve inspection in 4,000 hours.", 70),
        ("INSP-P-1101A-seal-inspection.pdf", "P-1101A", "Seal inspection, crude feed pump P-1101A",
         "Mechanical seal HAL-MS-4471 revision B removed after 7,600 operating hours. Primary face wear 0.3 mm, "
         "secondary seal elastomer hardened. Replaced with the same revision. Result: satisfactory.", 85),
        ("INSP-P-3101A-bearing-condition.pdf", "P-3101A", "Bearing condition report, cooling water pump P-3101A",
         "Drive end bearing temperature 78 degC at rated load, vibration 3.1 mm/s. Oil sample clean. Result: "
         "satisfactory.", 40),
        ("INSP-XV-1102-stroke-test.pdf", "XV-1102", "Stroke test record, emergency isolation valve XV-1102",
         "Closure time 6.4 seconds against the 8 second limit. No leakage on the seat test. Result: passed.", 220),
        ("INSP-XV-6101-leak-test.pdf", "XV-6101", "Leak test, tank outlet valve XV-6101",
         "Seat leakage rate class IV achieved. Actuator travel confirmed. Result: passed.", 55),
    ]
    for i, (fn, tag, title, body, days) in enumerate(inspections):
        add(fn, "inspection_report", 4, tag, title,
            f"Inspector: {PERSON['ins-1'].name}\nEquipment: {tag}\n\nFindings. {body}\n", days=days, rev="A",
            owner=PERSON["ins-1"].name)

    # --- Regulatory summaries (authority 1) --------------------------------------------------
    regs = [
        ("REG-work-permit-system-summary.pdf", "XV-1101", "Work permit system, statutory summary",
         "Hot work, confined space entry and high pressure line breaking require a written permit to work issued by "
         "an authorised issuer. The permit names the equipment, the isolation boundary and the person receiving it. "
         "Two independent signatures are required before safety-critical work begins. Permits are kept for three years."),
        ("REG-pressure-vessel-inspection-summary.pdf", "V-2101", "Pressure vessel inspection, statutory summary",
         "Pressure vessels such as V-1101, V-2101 and R-2101 are inspected at intervals set by a competent person. "
         "Safety valves are tested and reset at least every two years. Records of every inspection and test are kept "
         "for the life of the vessel."),
        ("REG-storage-tank-operation-summary.pdf", "T-6101", "Storage tank operation, statutory summary",
         "Flammable liquid tanks must have independent overfill protection, a tested vent relief valve and a fire "
         "water supply. Gauging equipment is checked at least weekly and the results recorded."),
    ]
    for i, (fn, tag, title, body) in enumerate(regs):
        add(fn, "regulation", 1, tag, title, f"Summary of statutory requirements.\n\n{body}\n", days=700, rev="A", owner="Compliance register")

    # --- Permits and shift logs ---------------------------------------------------------------
    add("PTW-CDU-pump-seal-replacement.txt", "ptw", 4, "P-1101A", "Permit to work: seal replacement on crude feed pump P-1101A",
        "Permit PTW-DEMO-0412. Work: replace the mechanical seal on P-1101A. Isolation boundary: suction and discharge "
        "valves of P-1101A closed and locked, motor breaker locked out, casing drained. Equipment on the boundary: "
        "P-1101A, XV-1101 and XV-1102. Issuing engineer: Prakash Menon. Receiver: Ravi Solanki. Valid for one shift.\n",
        days=20, mime="text/plain", owner=PERSON["eng-1"].name)
    add("PTW-HDT-compressor-valve-change.txt", "ptw", 4, "K-2101A", "Permit to work: valve change on recycle compressor K-2101A",
        "Permit PTW-DEMO-0438. Work: change second stage discharge valves on K-2101A. Isolation: compressor "
        "depressurised and purged with nitrogen, breaker locked out, suction and discharge isolation valves closed. "
        "Equipment on the boundary: K-2101A, XV-2101 and XV-2102. Issuing engineer: Lata Deshmukh.\n",
        days=12, mime="text/plain", owner=PERSON["eng-2"].name)
    add("PTW-TKF-tank-entry.txt", "ptw", 4, "T-6103", "Permit to work: confined space entry into tank T-6103",
        "Permit PTW-DEMO-0455. Work: internal cleaning of tank T-6103. Isolation: all inlet and outlet valves "
        "XV-6103 and XV-6104 blanked, tank gas-freed and tested. Entry requires a standby person and a rescue plan. "
        "Issuing engineer: Gopal Iyer.\n", days=6, mime="text/plain", owner=PERSON["ins-1"].name)
    add("PTW-UTL-boiler-burner-service.txt", "ptw", 4, "B-3101", "Permit to work: burner service on package boiler B-3101",
        "Permit PTW-DEMO-0461. Work: replace the main burner igniter on B-3101. Isolation: fuel gas double block and "
        "bleed closed, boiler off line and cooled. Equipment on the boundary: B-3101, XV-3101 and XV-3102.\n",
        days=3, mime="text/plain", owner=PERSON["hse-1"].name)

    logs = [
        ("SHIFTLOG-CDU-week-1.txt", "P-1101A", 56, "CDU", "shift-a"),
        ("SHIFTLOG-CDU-week-3.txt", "P-1102A", 42, "CDU", "shift-b"),
        ("SHIFTLOG-HDT-week-2.txt", "K-2101A", 49, "HDT", "shift-c"),
        ("SHIFTLOG-HDT-week-4.txt", "P-2101A", 28, "HDT", "shift-a"),
        ("SHIFTLOG-TKF-week-3.txt", "T-6101", 35, "TKF", "shift-b"),
        ("SHIFTLOG-UTL-week-4.txt", "P-3101A", 21, "UTL", "shift-c"),
    ]
    for fn, tag, days, unit, lead in logs:
        lead_name = PERSON[lead].name
        add(fn, "shift_log", 5, tag, f"Shift log, {unit}, week commencing {issued(days):%d %B}",
            f"Shift lead: {lead_name}\n\n"
            f"06:10 Took over from the previous shift. {tag} running normally, discharge pressure steady.\n"
            f"09:40 Walk-round of the {unit} unit. Slight oil mist near the drive end of {tag}; reported to the technician.\n"
            f"11:25 Radio check with the control room. Alarm acknowledged on the {unit} panel.\n"
            f"14:05 Handover meeting with the process engineer. Open work orders reviewed.\n"
            f"15:50 Housekeeping complete, permits closed. Handed over to the next shift lead.\n",
            days=days, mime="text/plain", owner=lead_name)

    # --- Per-asset records: bring every piece of equipment to RECORDS_PER_ASSET documents ----------
    have = {}
    for d in docs:
        have[d.asset_id] = have.get(d.asset_id, 0) + 1
    for asset in assets:
        if asset.equipment_class == UNIT or asset.tag in CONFLICT_BY_TAG or have.get(asset.asset_id, 0) >= RECORDS_PER_ASSET:
            continue
        rng = random.Random(f"records:{asset.tag}")
        facts, (test_title, test_lines), tasks, crew = _CLASS_RECORDS.get(asset.equipment_class, _DEFAULT_RECORD)(rng)
        maker, code = OEM.get(_oem_key(asset.equipment_class), ("Veridian procurement", "VPC"))
        installed = rng.randint(2008, 2022)
        wanted = RECORDS_PER_ASSET - have.get(asset.asset_id, 0)
        t = asset.tag
        records = [
            (f"DS-{t}-datasheet.pdf", "oem_manual", 3, f"Equipment datasheet, {t}",
             f"Manufacturer: {maker}. Model: {code} series {rng.choice('ABCDEFGH')}. Serial number: SN-{t}-{installed}.\n"
             f"Installed: {installed}. Unit: {asset.unit}. Criticality: {asset.criticality.replace('_', ' ')}. "
             f"Piping and instrument diagram: {asset.unit} unit, sheet {rng.choice(_SHEETS)}.\n\n" + "\n".join(facts) + "\n",
             rng.randint(500, 1800), PERSON["rel-1"].name),
            (f"TEST-{t}-record.pdf", "inspection_report", 4, f"{test_title}, {t}",
             f"Tester: {PERSON['ins-1'].name}\nEquipment: {t}\n\n" + "\n".join(test_lines) +
             f"\nResult: {rng.choice(['passed', 'passed', 'passed', 'passed with an observation'])}.\n",
             rng.randint(30, 400), PERSON["ins-1"].name),
            (f"MAINT-{t}-history-card.pdf", "inspection_report", 5, f"Maintenance history card, {t}",
             "\n".join(f"{(issued(rng.randint(20 + 120 * k, 110 + 120 * k))):%d %B %Y}: {task}, completed by "
                        f"{PERSON[rng.choice(crew)].name}. No defects found."
                        for k, task in enumerate(tasks)) + "\n\nNext preventive maintenance is raised by the planner.\n",
             rng.randint(10, 60), PERSON["plan-1"].name),
        ]
        for fn, dtype, authority, title, body, days, owner in records[:wanted]:
            # A year-stamped number ("DS-E-1103-2023") is recognised as a document reference, not a tag.
            add(fn, dtype, authority, t, title, body, days=days, rev="A", owner=owner,
                no=f"{fn.split('-', 1)[0]}-{t}-{issued(days).year}")

    # --- Failure history cards for the recurring failures, one dated line per work order. The routine
    # maintenance card above stays: it records preventive tasks, this one records the breakdowns. -------
    for tag, codes, days in CHAINS:
        rng = random.Random(f"chain:{tag}")
        lines = [f"{issued(d):%d %B %Y}: work order raised on {tag}. {DESC[codes[i % len(codes)]]}. "
                 f"Repaired by {PERSON[rng.choice(('tech-1', 'tech-2', 'tech-3', 'tech-4'))].name}, equipment returned to service."
                 for i, d in enumerate(days)]
        add(f"FAIL-{tag}-history-card.pdf", "inspection_report", 5, tag, f"Failure history card, {tag}",
            "\n".join(lines) + f"\n\nThis is failure {len(days)} in {days[0]} days on {tag}, roughly every "
            f"{round(days[0] / len(days))} days. The failure is recurring: the cause has not been removed by the "
            "repairs so far, and a reliability review of the duty is recommended.\n",
            days=max(1, days[-1] - 1), owner=PERSON["plan-1"].name, no=f"FAIL-{tag}-{issued(days[-1]).year}")

    names = [d.file_name for d in docs]
    assert len(names) == len(set(names)), "duplicate showcase document name"
    return docs
