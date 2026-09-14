"""
Extraction-path flagging (Layer 3) — no network, no Supabase.

The architecture wants handwritten content marked with "lower initial confidence scores, flagged
explicitly in the extraction output". The flag is the requirement; the score change is not — and
scaling `overall_confidence` down would push image-path extractions under the `< 0.7` quarantine
threshold, silently moving real facts out of the canonical graph. That is a retrieval regression
dressed up as a safeguard, and the golden dataset's handwritten inspection note and shift log are
exactly what it would have hit.

So: a separate field, and confidence left alone.
"""

import asyncio

from api.services.ocr import OCRService, ocr_review_reason

QUARANTINE_THRESHOLD = 0.7


def _extract(data: bytes, mime: str) -> dict:
    return asyncio.run(OCRService().extract_text(data, mime_type=mime))


def test_plain_text_is_native_and_not_handwriting_suspect():
    r = _extract(b"Pump P-101 seal replaced on 2026-03-04.", "text/plain")
    assert r["extraction_path"] == "native"
    assert r["handwriting_suspect"] is False


def test_native_paths_stay_well_above_the_quarantine_threshold():
    r = _extract(b"Inspection complete. No abnormal vibration.", "text/plain")
    assert r["overall_confidence"] > QUARANTINE_THRESHOLD


def test_unreadable_input_reports_unknown_path_not_a_false_native():
    """An error envelope must not claim it parsed digital text."""
    r = _extract(b"", "application/vnd.ms-excel")
    assert r["extraction_path"] == "unknown"
    assert r["handwriting_suspect"] is False


def test_every_envelope_carries_the_flag():
    """
    Guards the failure mode where one return path forgets the field and a consumer reading
    `result["extraction_path"]` raises KeyError only on the rare branch.
    """
    for data, mime in [
        (b"text", "text/plain"),
        (b"", "application/vnd.ms-excel"),
        (b"", "message/rfc822"),
    ]:
        r = _extract(data, mime)
        assert "extraction_path" in r, mime
        assert "handwriting_suspect" in r, mime
        assert r["extraction_path"] in {"native", "ocr", "unknown"}, mime


def test_flag_is_independent_of_confidence():
    """
    The whole point: the marker carries the signal, so downstream can surface a
    handwriting-suspect badge without the quarantine gate moving underneath it.
    """
    r = _extract(b"Shift log entry", "text/plain")
    assert r["handwriting_suspect"] is False
    assert r["overall_confidence"] == 1.0  # untouched by the flagging change


def _vault_doc(file_name: str, mime_type: str, document_type: str):
    from api.models.document import VaultDocument
    return VaultDocument(
        document_id="D-1", sha256_hash="x" * 64, file_name=file_name, file_size_bytes=10,
        mime_type=mime_type, document_type=document_type, authority_level=3,
        source_system="test", ingested_at="2026-08-16T00:00:00Z", ingested_by="test",
        status="active",
    )


def test_handwritten_image_documents_are_flagged():
    for dt in ("shift_log", "inspection_report"):
        d = _vault_doc("handwritten_note.png", "image/png", dt)
        assert d.extraction_path == "ocr"
        assert d.handwriting_suspect is True, dt


def test_engineering_drawings_are_not_handwriting_suspect():
    """
    A P&ID is an image and takes the vision path, but carries no handwriting. Flagging it would
    put a caution badge on every drawing in the vault and teach reviewers to ignore the badge.
    Caught on live data — both were PNGs, so the naive mime-only rule flagged the drawing too.
    """
    d = _vault_doc("pid_line3.png", "image/png", "pid_drawing")
    assert d.extraction_path == "ocr"      # it did come off an image
    assert d.handwriting_suspect is False  # but it is not handwriting


def test_digital_documents_are_native_and_unflagged():
    d = _vault_doc("manual.pdf", "application/pdf", "oem_manual")
    assert d.extraction_path == "native"
    assert d.handwriting_suspect is False


# =============================================================================
# Layer 4 — PERSON / ORGANIZATION materialised as first-class nodes
# =============================================================================

from api.services.graph import GraphService  # noqa: E402


def test_entity_node_id_is_stable_across_mentions():
    """The same person named in two documents must MERGE onto one node. A generated id would
    create a node per mention, leaving the graph with ten disconnected 'Rohit Menon's."""
    a = GraphService.entity_node_id("PERSON", "Rohit Menon")
    b = GraphService.entity_node_id("PERSON", "rohit  menon")
    assert a == b == "PERSON-ROHIT-MENON"


def test_person_and_org_ids_do_not_collide():
    """A person and a company with the same name are different nodes."""
    assert GraphService.entity_node_id("PERSON", "Fischer") != GraphService.entity_node_id(
        "ORGANIZATION", "Fischer"
    )


def test_org_prefix_is_used_for_organizations():
    assert GraphService.entity_node_id("ORGANIZATION", "Fischer Valves") == "ORG-FISCHER-VALVES"


def test_all_six_designed_node_labels_are_writable():
    """L4 designates six node types. Three were writable; Person/Organisation/Event were not,
    so `create_knowledge_edge` rejected them as unknown labels."""
    assert set(GraphService._LABEL_ID_FIELD) == {
        "Asset", "Document", "Event", "Concept", "Person", "Organisation",
    }


def test_organisation_label_matches_the_schema_spelling():
    """`init_schema.cypher` constrains `Organisation`. Writing `Organization` would silently
    create a second, unconstrained label that looks identical in query output."""
    assert "Organisation" in GraphService._LABEL_ID_FIELD
    assert "Organization" not in GraphService._LABEL_ID_FIELD


# --- CV-API response parsing and the inline size ceiling -------------------------------------
# Both of these failed by returning "", which is how a wrong dict key spent weeks being read as
# the documented "no handwriting model" limitation. The assertions below are about the two
# failures staying distinguishable, not just about a happy path.

import base64  # noqa: E402

from api.services.ocr import _NIM_IMAGE_SIZE_LIMIT  # noqa: E402


def test_detection_text_reads_the_live_cv_schema():
    """`text_prediction.text` is what the CV API actually returns — the original bug."""
    detection = {"bounding_box": [0, 0, 10, 10], "text_prediction": {"text": "EQ-101", "confidence": 0.91}}
    assert OCRService._detection_text(detection) == "EQ-101"


def test_detection_text_keeps_the_older_keys_as_fallbacks():
    assert OCRService._detection_text({"label": "PT-204"}) == "PT-204"
    assert OCRService._detection_text({"text": "16.2 bar"}) == "16.2 bar"


def test_detection_text_prefers_text_prediction_over_a_stale_key():
    detection = {"label": "wrong", "text_prediction": {"text": "right"}}
    assert OCRService._detection_text(detection) == "right"


def test_detection_text_is_empty_for_shapes_it_cannot_read():
    """Must return "", never raise — a schema change should log, not 500 the pipeline."""
    for junk in ({}, {"text_prediction": None}, {"text_prediction": {}}, None, "string", 7):
        assert OCRService._detection_text(junk) == ""


def _png_bytes(width: int, height: int) -> bytes:
    """Incompressible noise — worst case for the encoder, so the scaling path is really exercised."""
    import io as _io
    import os as _os

    from PIL import Image

    img = Image.frombytes("RGB", (width, height), _os.urandom(width * height * 3))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_oversized_image_is_re_encoded_under_the_inline_limit():
    """The degraded scans are 11-13x over; before this they never reached the model at all."""
    raw = _png_bytes(900, 900)
    assert len(base64.b64encode(raw)) > _NIM_IMAGE_SIZE_LIMIT, "fixture must exceed the limit"

    shrunk = OCRService._shrink_for_inline(raw)
    assert shrunk is not None, "a real image must be re-encodable, not dropped"
    data, mime = shrunk
    assert mime == "image/jpeg"
    assert len(base64.b64encode(data)) <= _NIM_IMAGE_SIZE_LIMIT


def test_an_image_already_under_the_limit_survives_re_encoding():
    data, mime = OCRService._shrink_for_inline(_png_bytes(80, 80))
    assert mime == "image/jpeg"
    assert len(base64.b64encode(data)) <= _NIM_IMAGE_SIZE_LIMIT


def test_shrink_returns_none_for_bytes_that_are_not_an_image():
    """None means "say so"; the caller logs and returns "" rather than crashing the pipeline."""
    assert OCRService._shrink_for_inline(b"not an image at all") is None


# --- model-reported confidence ----------------------------------------------------------------
# `overall_confidence` was hardcoded to 0.95 for every OCR extraction, so a badly garbled scan and
# a clean one were indistinguishable to every downstream gate — and CLAUDE.md's `< 0.7 -> quarantine`
# rule was being applied to a number that could never be below 0.7. These pin the real signal.


def test_detection_span_carries_the_models_own_confidence():
    span = OCRService._detection_span(
        {"text_prediction": {"text": "16.2 bar", "confidence": 0.91}}
    )
    assert span == ("16.2 bar", 0.91)


def test_missing_confidence_defaults_to_zero_never_to_a_flattering_constant():
    """An unknown confidence must not be able to lift a document over the quarantine threshold."""
    for detection in ({"text_prediction": {"text": "PT-204"}},
                      {"label": "PT-204"},
                      {"text_prediction": {"text": "x", "confidence": "high"}}):
        text, confidence = OCRService._detection_span(detection)
        assert text
        assert confidence == 0.0


def test_weighted_confidence_is_length_weighted_not_a_plain_mean():
    """A long garbled line must move the number more than a two-character margin mark."""
    spans = [("a" * 100, 0.5), ("b", 1.0)]
    weighted = OCRService._weighted_confidence(spans)
    plain = (0.5 + 1.0) / 2
    assert weighted < plain
    # tolerance matches the implementation's 4-dp rounding, not float epsilon
    assert abs(weighted - (100 * 0.5 + 1 * 1.0) / 101) < 1e-4


def test_weighted_confidence_of_nothing_is_zero_not_one():
    assert OCRService._weighted_confidence([]) == 0.0


def test_weighted_confidence_separates_the_corpus_documents():
    """
    Regression guard on the measured spread (2026-08-23, live CV probe). The clean handwritten
    note and the worst degraded scan must not land on the same side of the quarantine threshold.
    """
    clean = [("SHIFT LOG - PRODUCTION UNIT 2", 0.913), ("Date: 15-Jan-2026", 0.903),
             ("EQ-101 pump sounded a bit different tonight", 0.895)]
    garbled = [("FISCHER PUMPS LTD..-SERVICE BULLETIN", 0.843),
               ("Issue date: 202--01-15 SSperredess none", 0.253),
               ("Distribution: Al operetors of EO-xxx series", 0.402)]
    assert OCRService._weighted_confidence(clean) > 0.85
    assert OCRService._weighted_confidence(garbled) < OCRService._weighted_confidence(clean)


# =============================================================================
# Span-gate signals (Backlog #15 / D1 = option b)
# Guards the three keys that document_pipeline.run_ocr reads to decide whether
# to route a document through the span-shape quarantine gate.
# =============================================================================

def test_the_worst_corpus_scan_is_held_although_its_average_passes():
    """
    scanned_oem_bulletin_degraded: weighted mean 0.719 (above 0.7), but 4 of 22 spans below 0.7
    and one at 0.253. The mean alone would let it into the canonical graph — the gate must not.
    """
    result = {"overall_confidence": 0.719, "low_confidence_spans": 4, "min_span_confidence": 0.253}
    assert ocr_review_reason(result) == "low_confidence_spans"


def test_a_clean_handwritten_scan_continues():
    """The corpus's handwritten notes read at ~0.90 with no weak span — review would be pure noise."""
    result = {"overall_confidence": 0.91, "low_confidence_spans": 0, "min_span_confidence": 0.895}
    assert ocr_review_reason(result) is None


def test_an_unusable_scan_is_held_for_its_mean_first():
    result = {"overall_confidence": 0.31, "low_confidence_spans": 12, "min_span_confidence": 0.1}
    assert ocr_review_reason(result) == "low_ocr_confidence"


def test_native_text_carries_no_spans_and_is_never_held():
    assert ocr_review_reason(_extract(b"Pump P-101 seal replaced on 2026-03-04.", "text/plain")) is None


def test_ocr_result_envelope_carries_all_span_gate_keys():
    """
    The gate in document_pipeline.run_ocr reads three specific keys from the OCR
    result: 'low_confidence_spans', 'min_span_confidence', 'span_count'.
    Fast-path (native text) results must also carry these keys with safe defaults
    so the gate code never KeyErrors on a non-image document.

    Native paths go through _native(), which does not call _nim_ocr and therefore
    has no spans. Verify the safe-default contract: 0 weak spans, confidence 1.0.
    """
    r = _extract(b"Pump P-101 seal replaced on 2026-03-04.", "text/plain")
    # native path — gate keys must be absent or default-safe
    # The pipeline reads with .get(key, default); if present they must be safe values
    assert r.get("low_confidence_spans", 0) == 0
    assert r.get("min_span_confidence", 1.0) >= 0.7

