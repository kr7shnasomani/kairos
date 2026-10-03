"""The showcase plant: sites, people and assets.

A fictional two-site operation, built to read like a real mid-size refinery and its tank farm. Every
asset id starts with `DEMO-` and every site is a showcase site (`api/services/tenant.py`), which is
what keeps all of it out of real accounts.

Deliberately NOT reused from the golden dataset: no tag, part number, person, vendor or document
name appears in both. The knowledge graph merges Person, Organisation and Concept nodes by text, so a
shared name would silently join the showcase to the real plant.
"""

from dataclasses import dataclass

from api.services.tenant import DEMO_GENERAL_ASSET, DEMO_PREFIX

SITE_A = "SITE_DEMO"
SITE_B = "SITE_DEMO_B"
FACILITY = {SITE_A: "BHC", SITE_B: "DTF"}
SITE_NAME = {SITE_A: "Bharuch Complex", SITE_B: "Dahej Tank Farm"}
PLANT_NAME = "Veridian Petrochemicals"

# Equipment classes contain the words the seeded regulations apply to ("pump", "vessel", "valve",
# "compressor"), so compliance findings for the showcase assets are real, computed findings.
PUMP = "rotating_centrifugal_pump"
HP_PUMP = "rotating_high_pressure_pump"
COMPRESSOR = "reciprocating_compressor"
VESSEL = "pressure_vessel"
COLUMN = "pressure_vessel_column"
EXCHANGER = "shell_tube_heat_exchanger"
HEATER = "fired_heater"
CONTROL_VALVE = "valve_control"
ISOLATION_VALVE = "valve_isolation"
RELIEF = "valve_pressure_relief"
TRANSMITTER = "instrument_transmitter"
TANK = "storage_tank"
UNIT = "process_unit"
LOADING = "loading_arm"

SAFETY, CRITICAL, NON_CRITICAL = "safety_critical", "critical", "non_critical"


@dataclass(frozen=True)
class Asset:
    asset_id: str
    tag: str
    name: str
    equipment_class: str
    criticality: str
    site_id: str
    parent: str | None
    unit: str  # unit code, for documents and events
    aliases: tuple[str, ...] = ()

    @property
    def facility_id(self) -> str:
        return FACILITY[self.site_id]


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    role: str
    email: str


# Fictional staff. The demo account is the one real login; these are names that appear on records.
PEOPLE = (
    Person("shift-a", "Kiran Joshi", "Shift lead, A shift", "kiran.joshi@veridian.example"),
    Person("shift-b", "Meera Pillai", "Shift lead, B shift", "meera.pillai@veridian.example"),
    Person("shift-c", "Arvind Nair", "Shift lead, C shift", "arvind.nair@veridian.example"),
    Person("rel-1", "Dr. Sunita Rao", "Reliability engineer", "sunita.rao@veridian.example"),
    Person("rel-2", "Farhan Qureshi", "Reliability engineer", "farhan.qureshi@veridian.example"),
    Person("eng-1", "Prakash Menon", "Process engineer, CDU", "prakash.menon@veridian.example"),
    Person("eng-2", "Lata Deshmukh", "Process engineer, HDT", "lata.deshmukh@veridian.example"),
    Person("ins-1", "Gopal Iyer", "Inspection engineer", "gopal.iyer@veridian.example"),
    Person("tech-1", "Ravi Solanki", "Maintenance technician, mechanical", "ravi.solanki@veridian.example"),
    Person("tech-2", "Imran Sheikh", "Maintenance technician, mechanical", "imran.sheikh@veridian.example"),
    Person("tech-3", "Dinesh Patel", "Instrument technician", "dinesh.patel@veridian.example"),
    Person("tech-4", "Anita Chauhan", "Electrical technician", "anita.chauhan@veridian.example"),
    Person("hse-1", "Rohit Bhatt", "HSE officer", "rohit.bhatt@veridian.example"),
    Person("plan-1", "Neha Kulkarni", "Maintenance planner", "neha.kulkarni@veridian.example"),
)
PERSON = {p.key: p for p in PEOPLE}

# People who are retiring: the off-boarding programmes are about them. Ids carry the showcase prefix.
EXPERTS = (
    ("DEMO-EXPERT-SKHANNA", "Suresh Khanna", "suresh.khanna@veridian.example", "pumps and seals"),
    ("DEMO-EXPERT-MDALAL", "Mohan Dalal", "mohan.dalal@veridian.example", "heaters and heat exchangers"),
    ("DEMO-EXPERT-VRAMAN", "Vasanthi Raman", "vasanthi.raman@veridian.example", "compressors and instrumentation"),
)


def _id(tag: str) -> str:
    return f"{DEMO_PREFIX}{tag}"


def _letters(n: int) -> str:
    return "ABCDEFGH"[:n]


def build_assets() -> list[Asset]:
    """About 140 assets: two sites, five units on site A and a tank farm on site B, three levels deep
    (unit, equipment, instrument). Parents always precede their children."""
    out: list[Asset] = []

    def unit(code: str, name: str, site: str) -> str:
        aid = _id(f"UNIT-{code}")
        out.append(Asset(aid, f"UNIT-{code}", name, UNIT, CRITICAL, site, None, code))
        return aid

    def eq(parent: str, code: str, tag: str, name: str, cls: str, crit: str, site: str,
           aliases: tuple[str, ...] = ()) -> str:
        aid = _id(tag)
        out.append(Asset(aid, tag, name, cls, crit, site, parent, code, aliases))
        return aid

    def pair(parent, code, prefix, num, name, cls, crit, site, n=2, alias_fmt=None):
        ids = []
        for letter in _letters(n):
            tag = f"{prefix}-{num}{letter}"
            aliases = (alias_fmt.format(letter=letter, num=num),) if alias_fmt else ()
            ids.append(eq(parent, code, tag, f"{name} {letter}", cls, crit, site, aliases))
        return ids

    def instruments(parent, code, tags, site, crit=CRITICAL):
        for tag, name in tags:
            eq(parent, code, tag, name, TRANSMITTER, crit, site)

    # --- Site A: Crude Distillation Unit -------------------------------------------------------
    u = unit("CDU", "Crude Distillation Unit", SITE_A)
    pair(u, "CDU", "P", "1101", "Crude feed pump", PUMP, CRITICAL, SITE_A, 2, "CDU feed pump {letter}")
    pair(u, "CDU", "P", "1102", "Reflux pump", PUMP, CRITICAL, SITE_A, 2, "Reflux pump {letter}")
    pair(u, "CDU", "P", "1103", "Bottoms pump", PUMP, CRITICAL, SITE_A, 2)
    pair(u, "CDU", "P", "1104", "Kerosene draw pump", PUMP, NON_CRITICAL, SITE_A, 2)
    desalter = eq(u, "CDU", "V-1101", "Desalter", VESSEL, CRITICAL, SITE_A, ("Desalter",))
    column = eq(u, "CDU", "C-1101", "Atmospheric column", COLUMN, SAFETY, SITE_A, ("Main fractionator",))
    drum = eq(u, "CDU", "V-1102", "Reflux drum", VESSEL, CRITICAL, SITE_A)
    heater = eq(u, "CDU", "H-1101", "Crude charge heater", HEATER, SAFETY, SITE_A, ("Crude furnace",))
    for i in range(1, 7):
        eq(u, "CDU", f"E-110{i}", f"Crude preheat exchanger {i}", EXCHANGER, CRITICAL if i < 4 else NON_CRITICAL, SITE_A)
    for letter in "ABCD":
        eq(u, "CDU", f"E-1107{letter}", f"Overhead condenser {letter}", EXCHANGER, CRITICAL, SITE_A)
    for i in range(1, 7):
        eq(u, "CDU", f"FV-110{i}", f"Flow control valve {i}", CONTROL_VALVE, CRITICAL if i < 3 else NON_CRITICAL, SITE_A)
    for i in range(1, 5):
        eq(u, "CDU", f"XV-110{i}", f"Emergency isolation valve {i}", ISOLATION_VALVE, SAFETY, SITE_A)
    for i in range(1, 5):
        eq(u, "CDU", f"PSV-110{i}", f"Pressure safety valve {i}", RELIEF, SAFETY, SITE_A)
    instruments(column, "CDU", [("PT-1101", "Column top pressure"), ("TT-1101", "Column top temperature"),
                                ("LT-1101", "Column bottom level")], SITE_A)
    instruments(heater, "CDU", [("TT-1102", "Heater outlet temperature"), ("FT-1101", "Heater pass flow")], SITE_A)
    instruments(desalter, "CDU", [("LT-1102", "Desalter interface level")], SITE_A)
    instruments(drum, "CDU", [("LT-1103", "Reflux drum level")], SITE_A, NON_CRITICAL)

    # --- Site A: Diesel Hydrotreater ----------------------------------------------------------
    u = unit("HDT", "Diesel Hydrotreater", SITE_A)
    pair(u, "HDT", "P", "2101", "Reactor charge pump", HP_PUMP, SAFETY, SITE_A, 2, "HDT charge pump {letter}")
    pair(u, "HDT", "P", "2102", "Wash water pump", PUMP, NON_CRITICAL, SITE_A, 2)
    comp = pair(u, "HDT", "K", "2101", "Recycle gas compressor", COMPRESSOR, SAFETY, SITE_A, 2, "Recycle compressor {letter}")
    reactor = eq(u, "HDT", "R-2101", "Hydrotreating reactor", VESSEL, SAFETY, SITE_A, ("Reactor",))
    eq(u, "HDT", "V-2101", "Hot high pressure separator", VESSEL, SAFETY, SITE_A)
    eq(u, "HDT", "V-2102", "Cold high pressure separator", VESSEL, CRITICAL, SITE_A)
    eq(u, "HDT", "C-2101", "Amine absorber", COLUMN, CRITICAL, SITE_A)
    eq(u, "HDT", "C-2102", "Product stripper", COLUMN, CRITICAL, SITE_A)
    eq(u, "HDT", "H-2101", "Reactor charge heater", HEATER, SAFETY, SITE_A)
    for i in range(1, 6):
        eq(u, "HDT", f"E-210{i}", f"Feed effluent exchanger {i}", EXCHANGER, CRITICAL if i < 3 else NON_CRITICAL, SITE_A)
    for i in range(1, 5):
        eq(u, "HDT", f"FV-210{i}", f"Hydrogen control valve {i}", CONTROL_VALVE, CRITICAL, SITE_A)
    for i in range(1, 4):
        eq(u, "HDT", f"XV-210{i}", f"Reactor isolation valve {i}", ISOLATION_VALVE, SAFETY, SITE_A)
    for i in range(1, 4):
        eq(u, "HDT", f"PSV-210{i}", f"Reactor relief valve {i}", RELIEF, SAFETY, SITE_A)
    instruments(reactor, "HDT", [("TT-2101", "Reactor bed 1 temperature"), ("TT-2102", "Reactor bed 2 temperature"),
                                 ("PT-2101", "Reactor inlet pressure"), ("AT-2101", "Hydrogen purity")], SITE_A)
    instruments(comp[0], "HDT", [("VT-2101A", "Compressor A vibration"), ("TT-2103", "Compressor A discharge temperature")], SITE_A)
    instruments(comp[1], "HDT", [("VT-2101B", "Compressor B vibration")], SITE_A)

    # --- Site A: Utilities --------------------------------------------------------------------
    u = unit("UTL", "Utilities", SITE_A)
    pair(u, "UTL", "P", "3101", "Cooling water pump", PUMP, CRITICAL, SITE_A, 3, "CW pump {letter}")
    pair(u, "UTL", "P", "3102", "Boiler feed water pump", HP_PUMP, CRITICAL, SITE_A, 2)
    eq(u, "UTL", "CT-3101", "Cooling tower", "cooling_tower", CRITICAL, SITE_A)
    pair(u, "UTL", "K", "3101", "Instrument air compressor", COMPRESSOR, CRITICAL, SITE_A, 2)
    eq(u, "UTL", "B-3101", "Package boiler", HEATER, SAFETY, SITE_A)
    eq(u, "UTL", "V-3101", "Steam drum", VESSEL, SAFETY, SITE_A)
    eq(u, "UTL", "V-3102", "Instrument air receiver", VESSEL, CRITICAL, SITE_A)
    for i in range(1, 4):
        eq(u, "UTL", f"XV-310{i}", f"Steam isolation valve {i}", ISOLATION_VALVE, CRITICAL, SITE_A)
    for i in range(1, 3):
        eq(u, "UTL", f"PSV-310{i}", f"Steam drum relief valve {i}", RELIEF, SAFETY, SITE_A)

    # --- Site A: Flare and relief -------------------------------------------------------------
    u = unit("FLR", "Flare and Relief System", SITE_A)
    knockout = eq(u, "FLR", "V-4101", "Flare knock-out drum", VESSEL, SAFETY, SITE_A)
    eq(u, "FLR", "V-4102", "Flare seal drum", VESSEL, SAFETY, SITE_A)
    pair(u, "FLR", "P", "4101", "Knock-out drum pump", PUMP, SAFETY, SITE_A, 2)
    eq(u, "FLR", "XV-4101", "Flare header isolation valve", ISOLATION_VALVE, SAFETY, SITE_A)
    eq(u, "FLR", "PSV-4101", "Flare header relief valve", RELIEF, SAFETY, SITE_A)
    instruments(knockout, "FLR", [("LT-4101", "Knock-out drum level")], SITE_A, SAFETY)

    # --- Site A: Blending and dispatch --------------------------------------------------------
    u = unit("BLD", "Blending and Dispatch", SITE_A)
    pair(u, "BLD", "P", "5101", "Blend pump", PUMP, CRITICAL, SITE_A, 3)
    pair(u, "BLD", "P", "5102", "Dispatch pump", PUMP, CRITICAL, SITE_A, 3)
    for i in range(1, 5):
        eq(u, "BLD", f"LA-510{i}", f"Loading arm {i}", LOADING, CRITICAL, SITE_A)
    for i in range(1, 5):
        eq(u, "BLD", f"XV-510{i}", f"Dispatch isolation valve {i}", ISOLATION_VALVE, CRITICAL, SITE_A)

    # --- Site B: tank farm --------------------------------------------------------------------
    u = unit("TKF", "Tank Farm", SITE_B)
    tanks = []
    for i in range(1, 9):
        tanks.append(eq(u, "TKF", f"T-610{i}", f"Product storage tank {i}", TANK, SAFETY if i <= 2 else CRITICAL, SITE_B,
                        (f"Tank {i}",)))
    for i, t in enumerate(tanks[:4], start=1):
        instruments(t, "TKF", [(f"LT-610{i}", f"Tank {i} level"), (f"TT-610{i}", f"Tank {i} temperature")], SITE_B)
    pair(u, "TKF", "P", "6101", "Tank transfer pump", PUMP, CRITICAL, SITE_B, 6, "Transfer pump {letter}")
    pair(u, "TKF", "P", "6201", "Fire water pump", PUMP, SAFETY, SITE_B, 3)
    for i in range(1, 7):
        eq(u, "TKF", f"XV-610{i}", f"Tank outlet valve {i}", ISOLATION_VALVE, SAFETY if i <= 2 else CRITICAL, SITE_B)
    for i in range(1, 4):
        eq(u, "TKF", f"PSV-610{i}", f"Tank vent relief valve {i}", RELIEF, SAFETY, SITE_B)
    for i in range(1, 4):
        eq(u, "TKF", f"LA-610{i}", f"Truck loading arm {i}", LOADING, CRITICAL, SITE_B)

    ids = [a.asset_id for a in out]
    assert len(ids) == len(set(ids)), "duplicate showcase asset id"
    assert all(a.asset_id.startswith(DEMO_PREFIX) for a in out)
    return out


# The placeholder asset that unowned showcase items (off-boarding answers, ad-hoc notes) hang off.
GENERAL_ASSET = Asset(
    DEMO_GENERAL_ASSET, "GENERAL", "Knowledge transfer and general notes", UNIT, NON_CRITICAL, SITE_A, None, "CDU",
)
