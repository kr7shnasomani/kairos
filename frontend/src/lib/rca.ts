import type { RcaPack } from "./types";

// RCA presets (production) + fixture packs (TEST ONLY — see rcaFor below).
// These packs are NOT a runtime fallback: getRcaPack rejects on failure and the page
// renders a retry, so an offline backend never yields invented hypotheses.

// Canonical asset IDs so the RCA pack actually populates against live data.
// (P-101/HX-301 are an alias / non-existent tag — they return an empty pack.)
export const RCA_PRESETS = [
  { asset_id: "EQ-101", failure_code: "SEAL-FAIL", label: "EQ-101, mechanical seal failure" },
  { asset_id: "HE-301", failure_code: "TUBE-FOUL", label: "HE-301, tube fouling" },
  { asset_id: "EQ-101", failure_code: "RELIEF-SET", label: "EQ-101, relief-valve setpoint (safety-critical)" },
];

const SEAL_PACK: RcaPack = {
  asset_id: "P-101",
  incident_date: "2026-07-02T09:00:00Z",
  failure_code: "SEAL-FAIL",
  timeline: [
    { event_type: "vibration_alarm", occurred_at: "2026-06-18T06:12:00Z", description: "Elevated vibration on P-101 drive end (7.1 mm/s RMS).", source: "neo4j" },
    { event_type: "thermal_cycling", occurred_at: "2026-06-24T14:40:00Z", description: "Discharge temperature swings matching the pre-failure signature from the 2025 incident.", source: "historian" },
    { event_type: "operator_note", occurred_at: "2026-06-28T22:05:00Z", description: "Field note: unusual vibration and intermittent seal weep observed. Not formally raised.", source: "quarantine" },
    { event_type: "work_order_created", occurred_at: "2026-07-02T09:00:00Z", description: "WO-88213 opened — mechanical seal failure, P-101.", source: "supabase" },
  ],
  hypotheses: [
    { hypothesis: "Thermal cycling beyond the OEM envelope degraded the seal faces, consistent with 3 of 4 prior failures.", evidence_weight: 0.82, sources: ["DOC-P101-FAILURE-HIST", "OEM-BULL-MS44-r3"] },
    { hypothesis: "Bearing wear introduced shaft deflection, loading the seal asymmetrically.", evidence_weight: 0.54, sources: ["DOC-P101-FAILURE-HIST"] },
    { hypothesis: "Incorrect seal variant (MS-4470-A) installed at the last overhaul.", evidence_weight: 0.37, sources: ["OEM-BULL-MS44-r3"] },
  ],
  supporting_documents: [
    { document_id: "DOC-P101-FAILURE-HIST", title: "EQ-101 Failure History Report", authority_level: 2, confidence: 0.91 },
    { document_id: "OEM-BULL-MS44-r3", title: "Seal Series MS-44 Service Bulletin r3", authority_level: 3, confidence: 0.88 },
  ],
  confidence: 0.85,
  refused: false,
  synthesis_available: true,
};

const FOUL_PACK: RcaPack = {
  asset_id: "HX-301",
  incident_date: "2026-06-30T08:00:00Z",
  failure_code: "TUBE-FOUL",
  timeline: [
    { event_type: "efficiency_drop", occurred_at: "2026-05-10T00:00:00Z", description: "Heat-transfer efficiency down 9% over baseline.", source: "historian" },
    { event_type: "feedwater_excursion", occurred_at: "2026-05-22T00:00:00Z", description: "Feed-water hardness excursion recorded upstream.", source: "historian" },
    { event_type: "work_order_created", occurred_at: "2026-06-30T08:00:00Z", description: "3rd fouling-related WO in 90 days.", source: "supabase" },
  ],
  hypotheses: [
    { hypothesis: "Feed-water hardness excursions are driving recurrent scaling — a systemic upstream issue, not an exchanger fault.", evidence_weight: 0.79, sources: ["DOC-HX3-FOULING"] },
    { hypothesis: "Clean-in-place interval is too long for current water quality.", evidence_weight: 0.48, sources: ["DOC-HX3-FOULING"] },
  ],
  supporting_documents: [
    { document_id: "DOC-HX3-FOULING", title: "HX-3xx fouling trend analysis", authority_level: 2, confidence: 0.86 },
  ],
  confidence: 0.8,
  refused: false,
  synthesis_available: true,
};

const REFUSED_PACK: RcaPack = {
  asset_id: "P-101",
  incident_date: "2026-07-01T00:00:00Z",
  failure_code: "RELIEF-SET",
  timeline: [
    { event_type: "setpoint_query", occurred_at: "2026-07-01T00:00:00Z", description: "Relief-valve setpoint under review.", source: "supabase" },
  ],
  hypotheses: [],
  supporting_documents: [
    { document_id: "OISD-117-6.4", title: "OISD-117 §6.4 — Relief device setting", authority_level: 1, confidence: 0.97 },
    { document_id: "SOP-PSV-004", title: "Pressure-relief device procedure", authority_level: 4, confidence: 0.9 },
  ],
  confidence: 0.4,
  refused: true,
  synthesis_available: false,
};

const SAFETY_CODES = ["RELIEF", "PRESSURE", "PSV", "INTERLOCK", "TORQUE"];

/**
 * TEST-ONLY fixture builder. Used by rca/page.test.tsx to mock `getRcaPack`.
 * Never import this from `api.ts` or any render path — returning it on a failed
 * request presents invented hypotheses as governed evidence.
 */
export function rcaFor(assetId: string, failureCode: string): RcaPack {
  const code = failureCode.toUpperCase();
  if (SAFETY_CODES.some((s) => code.includes(s))) return { ...REFUSED_PACK, asset_id: assetId, failure_code: failureCode };
  if (code.includes("FOUL") || assetId.toUpperCase().startsWith("HX")) return { ...FOUL_PACK, asset_id: assetId, failure_code: failureCode };
  return { ...SEAL_PACK, asset_id: assetId, failure_code: failureCode };
}
