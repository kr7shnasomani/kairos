"""Generate fresh, ingestable demo documents for the Kairos presentation.

WHY THIS EXISTS
  `POST /documents/ingest` dedups on SHA-256, so any file already in the vault returns
  `{"status": "duplicate"}` with no pipeline run. Every file under `dataset/` is already
  ingested. A live ingest demo therefore needs content the vault has never seen.

SAFETY OF THE CONTENT
  Every asset tag, person, OEM, part number and document-ID convention is taken from
  `dataset/00_Reference/00_KAIROS_CANON.md`. Each set introduces a property that **no other
  document in the corpus states** (an interval, a torque, a tolerance), so ingesting any
  number of sets cannot produce a contradiction and cannot raise a false conflict.

  Deliberately avoided: HE-3xx **pressure**. That is the 18.5 -> 16.2 bar blast-radius story
  (canon MHT-PB-2026-11) and a second opinion on it would corrupt the Beat 8 demo.

USAGE (from the repo root)
    docker exec kairos-backend-api python /app/scripts/make_demo_docs.py --out /tmp/demo --sets 6
    docker cp kairos-backend-api:/tmp/demo ./demo-ingest/sets

  Re-run any time for a fresh batch: PDFs carry a creation timestamp, so every run yields
  new SHA-256s even for identical text. One file = one ingest.
"""

import argparse
import pathlib

import fitz

M, W = 60, 495

# Each set states ONE property nothing else in the corpus states. Fischer -> pumps (EQ-1xx),
# Meridian -> heat exchangers (HE-3xx), matching canon's OEM assignments.
SETS = [
    dict(oem="FISCHER PUMPS LTD.", code="FP-SB", asset="EQ-101", floc="RPC-U2-L1-EQ101",
         kind="Centrifugal Feed Pump", part="FSL-2240B", prior="FP-SB-2025-04",
         prop="seal inspection interval", value="5,000 operating hours",
         detail="Units not subject to thermal cycling may retain the standard 8,000 hour interval.",
         spec="Gland follower torque", spec_val="47 N-m", spec_max="55 N-m",
         wo="WO-2026-0714", ins_asset="XV-204", ins_floc="RPC-L3-S2-XV204",
         ins_kind="Secondary Bleed Valve", ins_due="14-Jan-2028"),
    dict(oem="FISCHER PUMPS LTD.", code="FP-SB", asset="EQ-102", floc="RPC-U2-L2-EQ102",
         kind="Centrifugal Feed Pump", part="FSL-2240B", prior="FP-SB-2025-04",
         prop="bearing regreasing interval", value="2,400 operating hours",
         detail="Interval halves where ambient at the bearing housing exceeds 45 degrees C.",
         spec="Grease charge per bearing", spec_val="18 grams", spec_max="25 grams",
         wo="WO-2026-0731", ins_asset="XV-203", ins_floc="RPC-L3-S2-XV203",
         ins_kind="Primary Isolation Valve", ins_due="12-Nov-2026"),
    dict(oem="FISCHER PUMPS LTD.", code="FP-SB", asset="EQ-103", floc="RPC-U2-L3-EQ103",
         kind="Centrifugal Feed Pump", part="FSL-2240B", prior="FP-SB-2025-04",
         prop="coupling alignment tolerance", value="0.05 mm parallel offset",
         detail="Angular misalignment is not to exceed 0.03 mm per 100 mm of coupling diameter.",
         spec="Cold alignment check interval", spec_val="12 months", spec_max="18 months",
         wo="WO-2026-0742", ins_asset="V-247", ins_floc="RPC-L3-S2-V247",
         ins_kind="Manual Isolation Valve", ins_due="20-Sep-2027"),
    dict(oem="MERIDIAN HEAT TRANSFER SYSTEMS", code="MHT-PB", asset="HE-301", floc="RPC-U1-HE301",
         kind="Shell and Tube Heat Exchanger", part="HE-3xx series", prior="MHT-PB-2026-11",
         prop="tube bundle cleaning interval", value="18 months",
         detail="Interval shortens to 12 months where fouling factor exceeds 0.0004 m2K/W.",
         spec="Channel cover bolt torque", spec_val="210 N-m", spec_max="240 N-m",
         wo="WO-2026-0755", ins_asset="PG-18", ins_floc="RPC-L3-S2-PG18",
         ins_kind="Local Gauge Bypass", ins_due="30-Nov-2027"),
    dict(oem="MERIDIAN HEAT TRANSFER SYSTEMS", code="MHT-PB", asset="HE-302", floc="RPC-U1-HE302",
         kind="Shell and Tube Heat Exchanger", part="HE-3xx series", prior="MHT-PB-2026-11",
         prop="shell-side gasket replacement interval", value="every second opening",
         detail="Spiral wound gaskets are single use and are not to be re-seated once compressed.",
         spec="Gasket seating stress", spec_val="55 MPa", spec_max="70 MPa",
         wo="WO-2026-0768", ins_asset="XV-204", ins_floc="RPC-L3-S2-XV204",
         ins_kind="Secondary Bleed Valve", ins_due="02-Apr-2028", ins_q="Q4", ins_date="02-Oct-2026"),
    dict(oem="MERIDIAN HEAT TRANSFER SYSTEMS", code="MHT-PB", asset="HE-303", floc="RPC-U1-HE303",
         kind="Shell and Tube Heat Exchanger", part="HE-3xx series", prior="MHT-PB-2026-11",
         prop="approach temperature alarm threshold", value="8 degrees C",
         detail="A sustained approach above this value for 72 hours indicates progressive fouling.",
         spec="Trend review interval", spec_val="weekly", spec_max="monthly",
         wo="WO-2026-0779", ins_asset="XV-203", ins_floc="RPC-L3-S2-XV203",
         ins_kind="Primary Isolation Valve", ins_due="09-Apr-2028", ins_q="Q4", ins_date="09-Oct-2026"),
]


def _doc(path, title, subtitle, fields, blocks):
    d = fitz.open()
    p = d.new_page()
    y = 62
    p.insert_text((M, y), title, fontname="hebo", fontsize=14)
    y += 19
    p.insert_text((M, y), subtitle, fontname="helv", fontsize=9)
    y += 10
    p.draw_line(fitz.Point(M, y), fitz.Point(M + W, y))
    y += 20
    for k, v in fields:
        p.insert_text((M, y), f"{k}:", fontname="hebo", fontsize=9.5)
        p.insert_text((M + 155, y), v, fontname="helv", fontsize=9.5)
        y += 15
    y += 8
    for head, body in blocks:
        p.insert_text((M, y), head, fontname="hebo", fontsize=10.5)
        y += 15
        r = fitz.Rect(M, y - 10, M + W, y + 200)
        y += (200 - p.insert_textbox(r, body, fontname="helv", fontsize=9.5, lineheight=1.45)) + 14
    d.save(str(path))
    d.close()


def build_set(out: pathlib.Path, i: int, c: dict) -> list[pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    bid = f"{c['code']}-2026-{20 + i:02d}"
    written = []

    f = out / f"oem_bulletin_{bid.lower().replace('-', '_')}.pdf"
    _doc(f, f"{c['oem']}  -  SERVICE BULLETIN",
         f"Document {bid}   |   Issued 20-Aug-2026   |   Supplementary to {c['prior']}",
         [("Bulletin reference", bid), ("Issue date", "20-Aug-2026"),
          ("Applies to", c["asset"]), ("Equipment class", c["kind"]),
          ("Component", c["part"]), ("Classification", "Advisory - recommended practice"),
          ("Supersedes", f"None. Supplements {c['prior']}, which remains in force.")],
         [("1. PURPOSE",
           f"This bulletin issues supplementary maintenance guidance for {c['asset']}. It does not "
           f"revise any part number, material or rating published in {c['prior']}, which remains the "
           "controlling document."),
          (f"2. RECOMMENDED {c['prop'].upper()}",
           f"For {c['asset']}, {c['oem'].title()} recommends a {c['prop']} of {c['value']}. "
           f"{c['detail']}"),
          (f"3. {c['spec'].upper()}",
           f"{c['spec']} for {c['asset']} is specified as {c['spec_val']}. Values beyond "
           f"{c['spec_max']} are outside the qualified range and are the most common installation "
           "defect reported to service centres."),
          ("4. ACTION REQUIRED",
           f"Site reliability engineering to align planned maintenance for {c['asset']} with Section 2 "
           "at the next scheduling review. No immediate shutdown action is required.")])
    written.append(f)

    f = out / f"{c['wo'].lower().replace('-', '_')}_closeout.pdf"
    _doc(f, "RAJGARH PETROCHEMICAL COMPLEX  -  WORK ORDER CLOSEOUT",
         f"Document {c['wo']}-CO   |   {c['floc']}   |   Closed 16-Jul-2026",
         [("Work order", c["wo"]), ("Asset tag", c["asset"]),
          ("Functional location", c["floc"]), ("Description", c["kind"]),
          ("Opened", "15-Jul-2026"), ("Closed", "16-Jul-2026"),
          ("Technician", "Suresh Yadav"),
          ("Verified by", "Ananya Iyer, Reliability Engineer"),
          ("Total downtime", "9.5 hours")],
         [("1. WORK PERFORMED",
           f"Planned maintenance executed on {c['asset']} at {c['floc']}. Asset isolated and returned "
           f"to service the following shift. Condition on strip-down was consistent with the "
           f"{c['prop']} guidance issued under {bid}."),
          ("2. PARTS AND CONSUMABLES",
           f"Component {c['part']} confirmed as the fitted revision. No superseded part numbers were "
           "drawn from stores for this work order."),
          ("3. INSTALLATION RECORD",
           f"{c['spec']} set to {c['spec_val']}, within the qualified range and below the "
           f"{c['spec_max']} limit. Post-work run test completed with no exception raised."),
          ("4. RELIABILITY NOTE",
           f"Reliability engineering to fold the {c['prop']} of {c['value']} into the planned "
           f"maintenance schedule for {c['asset']} at the next review.")])
    written.append(f)

    iq = c.get("ins_q", "Q3")
    idate = c.get("ins_date", "14-Jul-2026")
    iid = f"INSP-{c['ins_asset'].replace('-', '')}-2026-{iq}"
    f = out / f"{iid.lower().replace('-', '_')}.pdf"
    _doc(f, "RAJGARH PETROCHEMICAL COMPLEX  -  INSPECTION RECORD",
         f"Document {iid}   |   {c['ins_floc']}   |   {idate}",
         [("Inspection reference", iid), ("Asset tag", c["ins_asset"]),
          ("Functional location", c["ins_floc"]), ("Description", c["ins_kind"]),
          ("Inspection date", idate), ("Inspector", "Suresh Yadav"),
          ("Interval", "18 months"), ("Next due", c["ins_due"]),
          ("Result", "Satisfactory - no defects recorded")],
         [("1. SCOPE",
           f"Routine interval inspection of {c['ins_kind'].lower()} {c['ins_asset']} at "
           f"{c['ins_floc']}."),
          ("2. FINDINGS",
           "Body and bonnet free of external corrosion. Operated through full travel without binding. "
           "Seat leakage test passed at the rated differential. Gland packing shows no weeping. "
           "Position indicator agrees with valve state."),
          ("3. ISOLATION BOUNDARY NOTE",
           f"{c['ins_asset']} forms part of the Line 3 Section 2 isolation boundary used for permit to "
           "work. No change to the boundary configuration was made during this inspection."),
          ("4. RESULT",
           f"Accepted for continued service. Next inspection due {c['ins_due']} on the standing 18 "
           "month interval.")])
    written.append(f)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--sets", type=int, default=len(SETS),
                    help=f"how many sets to build (1-{len(SETS)})")
    a = ap.parse_args()
    if not 1 <= a.sets <= len(SETS):
        raise SystemExit(f"--sets must be 1..{len(SETS)}")

    root = pathlib.Path(a.out)
    for i in range(a.sets):
        c = SETS[i]
        d = root / f"set{i + 1:02d}"
        files = build_set(d, i, c)
        print(f"set{i + 1:02d}  {c['asset']:<7} {c['prop']:<38} {c['value']}")
        for f in files:
            print(f"          {f.name}")


if __name__ == "__main__":
    main()
