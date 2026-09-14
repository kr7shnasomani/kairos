# Kairos Demo Dataset — Canon Reference

**Purpose:** Single source of truth for every fact used across the dataset. Every file generated in Phases 1–4 must pull dates, tag numbers, and narrative details from here — nothing gets independently invented downstream. If a new fact is needed later, it gets added here first.

**Sector:** Petrochemical / process industry, India
**Facility:** Rajgarh Petrochemical Complex (RPC), Gujarat
**Demo Day ("today" in-story):** 15-Jul-2026

---

## 1. Personnel Directory

| Name | Role | Used in |
|---|---|---|
| Suresh Yadav | Field Technician, Production Unit 2 | Flow A (work order), quarantine vibration note |
| Rohit Menon | Process Engineer | Flow B (PTW issuer) |
| Vikram Desai | Shift Lead | Flow B (co-sign) |
| Ananya Iyer | Reliability Engineer | Layer 0/10 reviewer, quarantine owner |
| Priya Nair | Quality & Compliance Officer | Compliance cockpit persona |

**OEMs:** Fischer Pumps Ltd. (rotating equipment) · Meridian Heat Transfer Systems (heat exchangers)

---

## 2. Asset Registry

| Tag | Description | Location | Criticality | Class | Aliases |
|---|---|---|---|---|---|
| EQ-101 | Centrifugal Feed Pump | Prod Unit 2, Line 1 | Critical | Rotating – Centrifugal Pump | P-101, Pump 101, Feed Pump A, P101, "the old Fischer" |
| EQ-102 | Centrifugal Feed Pump | Prod Unit 2, Line 2 | High | Rotating – Centrifugal Pump | P-102, Pump 102, Feed Pump B |
| EQ-103 | Centrifugal Feed Pump | Prod Unit 2, Line 3 | High | Rotating – Centrifugal Pump | P-103, Pump 103, Feed Pump C |
| V-247 | Manual Isolation Valve | Prod Line 3, Sec 2 | Medium | Valve – Gate | — |
| XV-203 | Primary Isolation Valve | Prod Line 3, Sec 2 | Critical (safety isolation) | Valve – Isolation | — |
| XV-204 | Secondary Bleed Valve | Prod Line 3, Sec 2 | Medium | Valve – Isolation | Installed 2023, no failure history |
| PG-18 | Local Gauge Bypass | Prod Line 3, Sec 2 | Low–Medium | Instrument – Bypass | — |
| HE-301/302/303 | Shell & Tube Heat Exchangers | Prod Unit 1 | High | HE-3xx series | — |

EQ-101 installed 2010. XV-203 last inspected 12-May-2025, 18-month interval (next due 12-Nov-2026).

---

## 3. Master Timeline (chronological — the spine of every downstream document)

| Date | Event | Doc ID |
|---|---|---|
| 15-Jul-2018 | EQ-101 Failure #1 — mechanical seal, general wear | WO-2018-0412 |
| 2019 | EQ-102 seal failure (sister asset #1) | WO-2019-0206 |
| 22-Sep-2021 | EQ-101 Failure #2 — mechanical seal; thermal cycling noted retrospectively | WO-2021-0887 |
| 2022 | EQ-102 seal failure (sister asset #2) | WO-2022-0518 |
| 2023 | EQ-103 seal failure (sister asset #3) | WO-2023-0349 |
| **15-Jan-2025 (T-18mo)** | Fischer issues bulletin: seal P/N FSL-2240A → **FSL-2240B**, improved thermal cycling tolerance | FP-SB-2025-04 |
| 12-May-2025 | XV-203 formal inspection | INSP-XV203-2025-Q2 |
| **15-May-2025 (T-14mo)** | EQ-101 Failure #3 — mechanical seal, preceded by thermal cycling; repaired using **old P/N FSL-2240A** (bulletin hadn't reached maintenance stores/technician awareness) — *this gap is the story Kairos exists to close* | WO-2025-0631 |
| **15-Jan-2026 (T-6mo)** | Unverified: Suresh Yadav notes unusual vibration on EQ-101, not formally logged | (quarantine, no formal ID) |
| **1-Jun-2026** | Meridian issues bulletin: HE-3xx max operating pressure **18.5 bar → 16.2 bar** | MHT-PB-2026-11 (supersedes MHT-PB-2022-07) |
| 2-Mar-2026 | EQ-102 seal replaced (routine) | WO-2026-0203 |
| **22-Mar-2026 (+20 days)** | EQ-102 new fault — **electrical insulation** (different failure family) → counterfactual case, no confidence penalty on seal recommendation | WO-2026-0245 |
| **24-Jun-2026 (T-3wk)** | Unverified: PG-18 flagged — "may not be seating fully" | (quarantine, no formal ID) |
| **15-Jul-2026 — DEMO DAY** | Flow A: new WO opened, EQ-101, mechanical seal failure, assigned Suresh Yadav; live telemetry shows thermal cycling matching Failure #3 signature | WO-2026-0714 |
| **15-Jul-2026 — DEMO DAY** | Flow B: Rohit Menon issues PTW for V-247 isolation work; Vikram Desai co-signs | PTW-2026-0714 |

---

## 4. Documents Implied by Flow C (pressure revision) — to draft in Phase 2

Referenced in the architecture's blast-radius example; need corresponding docs so the graph linkage is real, not asserted:

| Doc | ID |
|---|---|
| Site operating procedures (×4, reference old 18.5 bar limit) | SOP-HE-301-04, SOP-HE-302-04, SOP-HE-303-04, SOP-HE-GEN-11 |
| Inspection records (×2, reference old spec) | INSP-HE301-2025-Q4, INSP-HE302-2025-Q4 |
| Maintenance procedure (hydrotest at 110% of operating pressure) | MP-HE-HYDROTEST-03 |

---

## 5. Document ID Conventions

| Type | Format |
|---|---|
| Work Order | WO-YYYY-NNNN |
| PTW | PTW-YYYY-NNNN |
| OEM Bulletin | [OEM-CODE]-SB/PB-YYYY-NN |
| Inspection Record | INSP-[ASSET]-YYYY-Q# |
| SOP | SOP-[ASSET/CLASS]-## |
| Maintenance Procedure | MP-[TOPIC]-## |

---

## 6. Open Item Before Phase 2

Regulatory clause references (OISD/PESO/Factories Act) will be pulled from real public sources via search when we build that document — not fabricated here, to avoid citing incorrect clause numbers.

---

## 7. Final File Manifest (as-built — matches dataset_manifest.csv exactly)

| # | File | Format | Layer(s) | Demo Flow | Notes |
|---|---|---|---|---|---|
| 1 | asset_registry.csv | CSV | Layer 1 (MDM Backbone) | General | 10 assets: EQ-101/102/103, V-247, XV-203/204, PG-18, HE-301/302/303 |
| 2 | alias_table.csv | CSV | Layer 1 (Alias Resolution) | General | 11 aliases incl. 'the old Fischer' for EQ-101 |
| 3 | work_orders_eq101_family.csv | CSV | Layer 4 / Layer 10 (Outcome Attribution) | A, General | 9 work orders: EQ-101 4x failures, sister assets, counterfactual pair |
| 4 | telemetry_eq101.csv | CSV | Layer 5 (OT Virtualization) | A, General | 140 readings: matching pre-failure ramps + baseline |
| 5 | oem_manual_eq1xx_seal.pdf | PDF | Layer 3 (Perception - native path) | A, General | Seal spec FSL-2240B; thermal cycling failure mode |
| 6 | oem_bulletin_fp_sb_2025_04.pdf | PDF | Layer 3, Layer 4 (Authority L3) | A | Seal P/N revision A to B; issued 15-Jan-2025 |
| 7 | oem_bulletin_mht_pb_2026_11.pdf | PDF | Layer 3, Layer 7 (Governance) | C | Pressure limit revision 18.5 to 16.2 bar |
| 8 | sop_he_301_04.pdf | PDF | Layer 4 (Authority L4) / Blast Radius | C | References superseded 18.5 bar limit |
| 9 | sop_he_302_04.pdf | PDF | Layer 4 / Blast Radius | C | References superseded 18.5 bar limit |
| 10 | sop_he_303_04.pdf | PDF | Layer 4 / Blast Radius | C | References superseded 18.5 bar limit |
| 11 | sop_he_gen_11.pdf | PDF | Layer 4 / Blast Radius | C | References superseded 18.5 bar limit |
| 12 | insp_he301_2025_q4.pdf | PDF | Layer 4 / Blast Radius | C | Inspection record citing old spec |
| 13 | insp_he302_2025_q4.pdf | PDF | Layer 4 / Blast Radius | C | Inspection record citing old spec |
| 14 | mp_he_hydrotest_03.pdf | PDF | Layer 4 / Blast Radius | C | Hydrotest calc dependent on pressure limit |
| 15 | regulatory_clause_excerpts.pdf | PDF | Layer 4 (Authority L1 - Regulatory) | General | Real OISD-STD-105/128/134; PESO Rules 2016; Factories Act S.31/36/87 |
| 16 | ptw_v247.pdf | PDF | Layer 3 (Form Parsing), Layer 8 | B | PTW-2026-0714 isolation boundary |
| 17 | work_order_closeout_form.pdf | PDF | Layer 3, Layer 10 | A | WO-2025-0631 closeout; old P/N used |
| 18 | inspection_checklist.pdf | PDF | Layer 3 (Form Parsing) | B | XV-203 inspection dated 12-May-2025 |
| 19 | pid_line3_isolation_boundary.png | PNG | Layer 3 (YOLOv9+LayoutLMv3 - mocked) | B | Isolation boundary XV-203/V-247/XV-204/PG-18 |
| 20 | scanned_oem_bulletin_degraded.png | PNG | Layer 3 (Perception - OCR path) | A | Same content as file 6; degraded for OCR contrast |
| 21 | scanned_inspection_degraded.png | PNG | Layer 3 (Perception - OCR path) | C | Same content as file 12; degraded for OCR contrast |
| 22 | handwritten_shift_log.png | PNG | Layer 3 (Handwriting Recognition) | A | Suresh Yadav EQ-101 vibration note dated 15-Jan-2026 |
| 23 | handwritten_inspection_note.png | PNG | Layer 3 (Handwriting Recognition) | B | Suresh Yadav PG-18 note dated 24-Jun-2026 |
| 24 | shift_log.txt | TXT | Layer 3 (NLP - English) | A, B | Same 2 events as files 22/23, English only for this test pass |
| 25 | event_work_order_creation.json | JSON | Layer 8 (Event Subscription) | A | WO-2026-0714 creation trigger |
| 26 | event_ptw_generation.json | JSON | Layer 8 | B | PTW-2026-0714 generation trigger |
| 27 | event_shift_handover.json | JSON | Layer 8 | General | End-of-shift brief content |
| 28 | event_recurring_failure.json | JSON | Layer 8, Layer 10 | General | EQ-102 counterfactual recurrence |
| 29 | quarantine_vibration_observation.json | JSON | Layer 6, Layer 9 | A | Structured version of files 22/24 entry 1 |
| 30 | quarantine_pg18_deviation.json | JSON | Layer 6 | B | Structured version of files 23/24 entry 2 |
| 31 | voice_note_transcript.txt | TXT | Layer 3 (Groq Whisper), Layer 9 (Elicitation) | A | WO-2025-0631 closeout micro-interview |
| 32 | voice_note_eq101.mp3 | MP3 | Layer 3 (Groq Whisper) | A | Audio version of file 31's Q3 answer, English only |

Status: all files complete and verified (see VERIFICATION_REPORT.md). Scope for this test pass is English-only -- multilingual/Hinglish support is deferred, not abandoned; see file 24 note.

---
*This document is the anchor. Update it first if any fact changes — everything else follows from it.*
