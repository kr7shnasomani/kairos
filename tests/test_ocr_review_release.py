"""Service-free: releasing a document held by the OCR gate re-runs extraction from the vault artifact."""

import pytest

from api.config import settings
from api.routers.documents import release_workflow_params, vault_storage_path

BUCKET = settings.SUPABASE_STORAGE_BUCKET
URL = f"https://x.supabase.co/storage/v1/object/authenticated/{BUCKET}/oem_manual/DOC-1/bulletin scan.png"


def test_the_vault_path_is_recovered_from_the_stored_url():
    assert vault_storage_path(URL) == "oem_manual/DOC-1/bulletin scan.png"


@pytest.mark.parametrize("url", [None, "", "https://x.supabase.co/storage/v1/object/public/other/file.png"])
def test_an_unrecognised_url_yields_no_path(url):
    assert vault_storage_path(url) is None


def test_release_params_mirror_ingestion_and_name_the_reviewer():
    doc = {"document_id": "DOC-1", "vault_url": URL, "mime_type": "image/png",
           "document_type": "oem_manual", "authority_level": 3}

    params = release_workflow_params(doc, "HE-301", "job-2", "reliability-7")

    assert params == {
        "document_id": "DOC-1", "vault_path": "oem_manual/DOC-1/bulletin scan.png", "mime_type": "image/png",
        "asset_id": "HE-301", "document_type": "oem_manual", "authority_level": 3,
        "job_id": "job-2", "ocr_reviewed_by": "reliability-7",
    }


def test_a_release_without_a_recoverable_artifact_is_refused():
    with pytest.raises(ValueError):
        release_workflow_params({"document_id": "DOC-1", "vault_url": None}, None, "job-2", "admin-1")


# =============================================================================
# OCR gate reference: a scan is scored against the one entry it reproduces
# =============================================================================

from api.services.ocr_gate import reference_entry, score_ocr  # noqa: E402

_LOG = """SHIFT LOG

---

Entry: 15-Jan-2026, Night Shift
EQ-101 pump felt more vibration than usual.

---

Entry: 24-Jun-2026, Day Shift
Moisture at the PG-18 gauge bypass.

---

Entry: 15-Jul-2026, Day Shift
New work order for EQ-101 (WO-2026-0714).
"""


def test_reference_entry_picks_the_declared_entry_only():
    block = reference_entry(_LOG, "24-Jun-2026")
    assert "PG-18" in block and "EQ-101" not in block and "WO-2026-0714" not in block


def test_reference_entry_falls_back_to_the_whole_reference():
    assert reference_entry(_LOG, None) == _LOG
    assert reference_entry(_LOG, "01-Feb-2026") == _LOG


def test_a_note_is_not_penalised_for_the_other_notes_event():
    note = "FIELD NOTE Date: 24-Jun-2026 PG-18 bypass gauge moisture"
    assert score_ocr(_LOG, note)["salient_recall"] < 0.5
    assert score_ocr(reference_entry(_LOG, "24-Jun-2026"), note)["salient_recall"] == 1.0


def test_a_misread_date_is_still_a_miss():
    note = "FIELD NOTE Date: 24-Jan-2026 PG-18 bypass gauge moisture"
    assert score_ocr(reference_entry(_LOG, "24-Jun-2026"), note)["salient_recall"] < 1.0
