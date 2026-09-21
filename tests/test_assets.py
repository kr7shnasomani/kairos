"""Assets — Tasks 1-3: MDM backbone, asset CRUD, aliases, hierarchy, knowledge graph."""

from tests.conftest import uid


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


async def test_create_asset_is_idempotent(admin_client):
    asset_id = f"ASSET-{uid()}"
    payload = {
        "asset_id": asset_id,
        "tag_number": f"TAG-{uid()}",
        "name": "Idempotent Pump",
        "equipment_class": "COMPRESSOR",
        "criticality": "non_critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    }
    r1 = await admin_client.post("/assets/", json=payload)
    r2 = await admin_client.post("/assets/", json=payload)
    assert r1.status_code == 201
    # Second call should not raise — MERGE in Neo4j is idempotent
    assert r2.status_code in (200, 201)


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
