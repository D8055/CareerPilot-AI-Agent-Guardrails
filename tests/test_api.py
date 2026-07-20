"""API smoke tests: the deterministic core works keyless, end to end."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["pool_bullets"] > 10


def test_tailor_returns_validated_plan(client):
    jd = "React and .NET developer with SQL, Docker, and data pipelines."
    r = client.post("/tailor", json={"jd_text": jd})
    assert r.status_code == 200
    body = r.json()
    assert body["match_score"] is not None and 0 < body["match_score"] <= 100
    assert "react" in body["matched_keywords"]
    assert body["plan"]["summary_text"]
    assert len(body["plan"]["projects"]) == 3
    assert body["honesty_violations"] == []


def test_tailor_rejects_empty_jd(client):
    assert client.post("/tailor", json={"jd_text": ""}).status_code == 422
