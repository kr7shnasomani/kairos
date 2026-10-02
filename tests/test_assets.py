"""Assets — Tasks 1-3: MDM backbone, asset CRUD, aliases, hierarchy, knowledge graph.

Security pass (2026-09-30 review, M8): single asset create is insert-only (a second post of an id is
a 409), and every asset route is site-scoped. A non-admin registers only on their own site and gets
the same 404 for another site's asset as for an unknown one.
"""

from tests.conftest import OTHER_SITE, uid


async def test_create_asset(admin_client):
    asset_id = f"ASSET-{uid()}"
    r = await admin_client.post("/assets/", json={
        "asset_id": asset_id,
        "tag_number": f"TAG-{uid()}",
        "name": "Test Pump Alpha",
        "equipment_class": "PUMP",
        "criticality": "critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["asset_id"] == asset_id
    assert body["status"] == "created"


async def test_create_asset_is_insert_only(admin_client):
    """Registering an id twice is a 409, and the first record is left exactly as it was."""
    asset_id = f"ASSET-{uid()}"
    payload = {
        "asset_id": asset_id,
        "tag_number": f"TAG-{uid()}",
        "name": "Insert-Only Pump",
        "equipment_class": "COMPRESSOR",
        "criticality": "non_critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    }
    r1 = await admin_client.post("/assets/", json=payload)
    r2 = await admin_client.post("/assets/", json={**payload, "name": "Overwrite attempt"})
    assert r1.status_code == 201
    assert r2.status_code == 409

    stored = await admin_client.get(f"/assets/{asset_id}")
    assert stored.status_code == 200
    assert stored.json()["name"] == "Insert-Only Pump"


async def test_create_asset_on_another_site_is_refused_for_an_existing_id(admin_client, shared_asset_id):
    """An id already registered on one site cannot be re-posted from another."""
    r = await admin_client.post("/assets/", json={
        "asset_id": shared_asset_id,
        "tag_number": f"TAG-{uid()}",
        "name": "Cross-site clobber",
        "equipment_class": "PUMP",
        "criticality": "critical",
        "site_id": OTHER_SITE,
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert r.status_code == 409


async def test_create_asset_auto_id(admin_client):
    """When asset_id is omitted the API generates one."""
    r = await admin_client.post("/assets/", json={
        "tag_number": f"TAG-{uid()}",
        "name": "Auto ID Asset",
        "equipment_class": "HEAT_EXCHANGER",
        "criticality": "non_critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert r.status_code == 201
    assert "asset_id" in r.json()


async def test_get_asset(admin_client, shared_asset_id):
    r = await admin_client.get(f"/assets/{shared_asset_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["asset_id"] == shared_asset_id
    assert "open_work_orders_count" in body
    assert "compliance_gap_count" in body


async def test_get_asset_not_found(admin_client):
    r = await admin_client.get("/assets/ASSET-DOES-NOT-EXIST-XYZ")
    assert r.status_code == 404


async def test_list_assets(admin_client, shared_asset_id):
    r = await admin_client.get("/assets/")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
    ids = [a["asset_id"] for a in body["items"]]
    # The shared fixture is an `ASSET-TEST-` id, so it is hidden from the list and counted instead
    # (services/corpus.py). Seeing it here would mean the test-asset filter is broken.
    assert shared_asset_id not in ids
    assert body["excluded_test_assets"] >= 1


async def test_list_assets_filter_site(admin_client, shared_asset_id):
    r = await admin_client.get("/assets/", params={"site_id": "SITE_001"})
    assert r.status_code == 200
    for asset in r.json()["items"]:
        assert asset["site_id"] == "SITE_001"


async def test_list_assets_filter_equipment_class(admin_client):
    r = await admin_client.get("/assets/", params={"equipment_class": "PUMP"})
    assert r.status_code == 200
    for asset in r.json()["items"]:
        assert asset["equipment_class"] == "PUMP"


async def test_get_asset_aliases(admin_client, shared_asset_id):
    r = await admin_client.get(f"/assets/{shared_asset_id}/aliases")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_get_asset_hierarchy(admin_client, shared_asset_id):
    r = await admin_client.get(f"/assets/{shared_asset_id}/hierarchy")
    assert r.status_code == 200
    body = r.json()
    assert "asset_id" in body or "children" in body or "parents" in body


async def test_get_asset_knowledge(admin_client, shared_asset_id):
    r = await admin_client.get(f"/assets/{shared_asset_id}/knowledge")
    assert r.status_code == 200
    body = r.json()
    assert body["asset_id"] == shared_asset_id
    assert "facts" in body
    assert "fact_count" in body
    assert isinstance(body["facts"], list)


async def test_get_asset_knowledge_as_of(admin_client, shared_asset_id):
    r = await admin_client.get(
        f"/assets/{shared_asset_id}/knowledge",
        params={"as_of": "2025-01-01T00:00:00Z"},
    )
    assert r.status_code == 200
    assert r.json()["as_of"] == "2025-01-01T00:00:00Z"


async def test_get_asset_knowledge_invalid_as_of(admin_client, shared_asset_id):
    r = await admin_client.get(
        f"/assets/{shared_asset_id}/knowledge",
        params={"as_of": "not-a-date"},
    )
    assert r.status_code == 422


async def test_field_worker_can_list_assets(field_client):
    r = await field_client.get("/assets/")
    assert r.status_code == 200


async def test_field_worker_cannot_create_asset(field_client):
    r = await field_client.post("/assets/", json={
        "tag_number": f"TAG-{uid()}",
        "name": "Unauthorized",
        "equipment_class": "PUMP",
        "criticality": "non_critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "field-worker",
    })
    # field_worker lacks admin/engineer role → 403
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Site scope
# ---------------------------------------------------------------------------

async def test_engineer_cannot_register_an_asset_on_another_site(engineer_client):
    r = await engineer_client.post("/assets/", json={
        "tag_number": f"TAG-{uid()}",
        "name": "Wrong site",
        "equipment_class": "PUMP",
        "criticality": "non_critical",
        "site_id": OTHER_SITE,
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "engineer",
    })
    assert r.status_code == 403


async def test_non_admin_cannot_list_another_site(engineer_client):
    r = await engineer_client.get("/assets/", params={"site_id": OTHER_SITE})
    assert r.status_code == 403


async def test_other_sites_asset_is_404_on_every_asset_route(engineer_client, other_site_asset_id):
    for suffix in ("", "/aliases", "/hierarchy", "/knowledge", "/ot-coverage"):
        r = await engineer_client.get(f"/assets/{other_site_asset_id}{suffix}")
        assert r.status_code == 404, suffix


async def test_admin_still_sees_other_sites(admin_client, other_site_asset_id):
    r = await admin_client.get(f"/assets/{other_site_asset_id}")
    assert r.status_code == 200
    assert r.json()["site_id"] == OTHER_SITE
