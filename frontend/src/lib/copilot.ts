import type { AuthorityLevel } from "./types";

// Display-oriented copilot response. Superset of the API's SynthesizeResponse
// with source titles/excerpts for rendering. api.ts maps POST /search/synthesize
// (+ the /search hits that formed its context) into this shape.
//
// Types and suggestions only — deliberately no fixture answers live here. The copilot
// renders live evidence, an empty result, or an error+retry; a stand-in answer would
// present invented document IDs as governed provenance.

export interface CopilotSource {
  document_id: string;
  title: string;
  authority_level: AuthorityLevel;
  excerpt: string;
  is_quarantine?: boolean;
  /** Opens the actual file in a new tab. Absent for a locally-answered meta question or if
   *  the vault record has no stored URL. */
  vault_url?: string;
}

/** An engineering conflict on a cited asset that is awaiting MoC sign-off. */
export interface PendingMoc {
  conflict_id: string;
  asset_id: string;
  parameter: string;
  severity: string;
  moc_id: string | null;
  moc_status: string | null;
}

export interface CopilotAnswer {
  answer: string | null;
  sources: CopilotSource[];
  /** `null` = the model reported no confidence, which is NOT the same as 0. The backend returns
   *  null whenever the synthesis output carries no parseable `CONFIDENCE:` marker — measured at
   *  ~23% of successful answers — and coercing that to 0 made the UI assert a low-confidence
   *  score the system never produced. Nullable on purpose so the compiler forces every reader
   *  to decide what "unknown" looks like. */
  confidence: number | null;
  refused: boolean;
  refusal_reason?: string;
  safety_critical: boolean;
  model?: string;
  /** Non-empty → the answer touches a parameter under formal dispute; the UI must say so. */
  pending_moc?: PendingMoc[];
  /** True while sources have been retrieved but synthesis is still running. */
  is_synthesizing?: boolean;
}

// Each one is checked against the live data: a cited history, a value under MoC, a value
// changed by a newer bulletin, and a safety question the gate refuses.
export const SUGGESTIONS = [
  "What's the failure history of P-1101A?",
  "What is the minimum continuous flow for P-1101A?",
  "Maximum allowable pressure for the HE-3xx series?",
  "Isolation points for work on V-247",
];

// ─── Meta questions ──────────────────────────────────────────────────────────
//
// "hello", "what can you do?", "help" are questions about the *assistant*, not about
// plant knowledge. Sending them down the retrieval pipeline retrieves nothing relevant,
// spends a synthesis call (p50 ~40 s) and returns either a refusal or a vague answer
// assembled from unrelated documents — which reads as the system being broken.
//
// These are answered locally instead. The reply describes the system and is rendered with
// NO sources, because it has none: it is not retrieved knowledge and must never be dressed
// up as such. Anything not matched here goes to the governed pipeline unchanged — this
// deliberately does not attempt small talk, and no plant fact is ever answered from here.

/** Marks a turn as locally answered, so the UI can label it and skip provenance chrome. */
export const META_MODEL = "kairos-meta";

const META_REPLIES: ReadonlyArray<{ test: RegExp; answer: string }> = [
  {
    test: /^\s*(hi|hey|hello|yo|good\s*(morning|afternoon|evening))\b/i,
    answer:
      "Hello. Ask me about an asset, a document, a procedure or a compliance clause and I'll answer " +
      "from governed sources with citations.\n\nTry: \"What's the failure history of P-1101A?\"",
  },
  {
    test: /\b(what can you do|what do you do|who are you|what are you|how do you work|what is kairos|help me|^\s*help\s*$|capabilities)\b/i,
    answer:
      "I answer questions about this plant's equipment from governed, cited sources.\n\n" +
      "**What I can do**\n" +
      "• Current facts about an asset — part numbers, ratings, OEM, equipment class\n" +
      "• History and supersession — what was true on a past date, and which document replaced which\n" +
      "• Traceability — which document and authority level a fact came from\n" +
      "• Compliance gaps and the evidence behind them\n" +
      "• Failure history, root-cause packs and blast radius\n\n" +
      "**How I answer**\n" +
      "Every claim carries its source document and authority level. Where evidence is weak I say so " +
      "rather than smoothing over it.\n\n" +
      "**What I refuse**\n" +
      "Safety-critical parameters — pressure limits, isolation boundaries, torque specs, relief " +
      "settings — when the evidence isn't authoritative enough. You get the source documents and an " +
      "escalation path instead of a confident guess.",
  },
];

/** A local answer for a meta question, or null to send the query to retrieval. */
export function metaAnswer(query: string): CopilotAnswer | null {
  const hit = META_REPLIES.find((r) => r.test.test(query));
  if (!hit) return null;
  return {
    answer: hit.answer,
    sources: [],
    confidence: 1,
    refused: false,
    safety_critical: false,
    model: META_MODEL,
  };
}
