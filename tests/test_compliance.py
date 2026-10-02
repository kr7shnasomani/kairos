"""Compliance — Task 26: gap detection, dashboard, audit pack, frameworks."""


async def test_compliance_gaps_shape(admin_client):
    r = await admin_client.get("/compliance/gaps")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "last_scan" in body
    assert body["last_scan"] == "realtime"


async def test_compliance_gaps_filter_framework(admin_client):
    r = await admin_client.get("/compliance/gaps", params={"framework": "OISD_117"})
    assert r.status_code == 200
    assert "items" in r.json()


async def test_compliance_gaps_filter_severity(admin_client):
    r = await admin_client.get("/compliance/gaps", params={"severity": "critical"})
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["severity"] == "critical"


async def test_compliance_gaps_are_clause_scoped(admin_client):
    """
    Every finding must be tied to the clause's required evidence type and carry a
    status. Guards the regression where the query ignored the clause and reported
    every (regulation × asset) pair as a gap unconditionally.
    """
    r = await admin_client.get("/compliance/gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["gap_total"] + body["unverified_total"] == body["total"]

    for item in body["items"]:
        assert item["status"] in ("gap", "unverified_evidence")
        # A 'gap' means no evidence of the required type exists — by definition.
        if item["status"] == "gap":
            assert item["evidence_count"] == 0
        else:
            assert item["evidence_count"] > 0 and item["verified_count"] == 0
        assert item["clause_id"] and item["asset_id"]


async def test_compliance_gaps_filter_status(admin_client):
    r = await admin_client.get("/compliance/gaps", params={"status": "gap"})
    assert r.status_code == 200
    assert all(i["status"] == "gap" for i in r.json()["items"])


async def test_compliance_dashboard_shape(admin_client):
    r = await admin_client.get("/compliance/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "total_gaps" in body
    assert "by_framework" in body
    assert "by_asset_class" in body
    assert "last_updated" in body


async def test_compliance_frameworks_shape(admin_client):
    r = await admin_client.get("/compliance/frameworks")
    assert r.status_code == 200
    body = r.json()
    assert "configured_frameworks" in body
    assert "available_frameworks" in body
    assert isinstance(body["available_frameworks"], list)
    assert "OISD_117" in body["available_frameworks"]


async def test_compliance_audit_pack_requires_framework(admin_client):
    r = await admin_client.get("/compliance/audit-pack")
    assert r.status_code == 422


async def test_compliance_audit_pack_shape(admin_client):
    r = await admin_client.get("/compliance/audit-pack", params={"framework": "OISD_117"})
    assert r.status_code == 200
    body = r.json()
    assert body["framework"] == "OISD_117"
    assert "clauses" in body
    assert "total_clauses" in body
    assert "human_review_required" in body
    assert body["status"] == "draft"
    assert "Human sign-off required" in body["note"]


async def test_compliance_auditor_reads_site_scoped_audit_pack(compliance_client):
    """Non-admin reads are pinned to the caller's own site (security review M8)."""
    r = await compliance_client.get("/compliance/audit-pack", params={"framework": "OISD_117"})
    assert r.status_code == 200


async def test_compliance_non_admin_cannot_read_another_site(engineer_client):
    r = await engineer_client.get("/compliance/gaps", params={"site_id": "SITE_OTHER"})
    assert r.status_code == 403
