"""Health endpoint — verifies all services are reachable."""



async def test_health_returns_200(anon_client):
    r = await anon_client.get("/health/")
    assert r.status_code == 200


async def test_health_response_shape(anon_client):
    r = await anon_client.get("/health/")
    body = r.json()
    assert "status" in body


async def test_health_detailed(admin_client):
    # Gated behind auth (security-review L7): five store round-trips per call is not public.
    r = await admin_client.get("/health/detailed")
    # 200 = all deps up; 503 = degraded but API is alive. Both are valid here.
    assert r.status_code in (200, 503)
    body = r.json()
    assert "checks" in body
    assert "neo4j" in body["checks"]
    assert "redis" in body["checks"]
