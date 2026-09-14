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
