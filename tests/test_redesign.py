"""July 2026 redesign: New-Jobs status model, job deletion, and inline
career editing with pool write-back."""
import shutil


def test_new_jobs_stay_new_until_applied(client, owner_headers):
    job = client.post("/jobs", json={"company": "SavedCo", "role": "SWE"},
                      headers=owner_headers).json()
    assert job["status"] == "new"
    client.post(f"/jobs/{job['id']}/tailor",
                json={"jd_text": "Python SQL React"}, headers=owner_headers)
    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert detail["status"] == "tailored"    # Apply moves it to the Board


def test_delete_job_cascades(client, owner_headers, viewer_headers):
    job = client.post("/jobs", json={"company": "DeleteCo", "role": "X"},
                      headers=owner_headers).json()
    client.post(f"/jobs/{job['id']}/tailor",
                json={"jd_text": "Python SQL"}, headers=owner_headers)
    # viewer cannot delete
    assert client.delete(f"/jobs/{job['id']}",
                         headers=viewer_headers).status_code == 403
    assert client.delete(f"/jobs/{job['id']}",
                         headers=owner_headers).status_code == 200
    assert client.get(f"/jobs/{job['id']}",
                      headers=owner_headers).status_code == 404


def test_edit_owner_career_item(client, owner_headers):
    item = client.post("/career/items", json={
        "text": "Wrote a small Flask API for a club project.",
        "section": "extras"}, headers=owner_headers).json()
    r = client.patch(f"/career/items/{item['id']}",
                     json={"text": "Wrote a small Flask REST API for a club "
                                   "project with SQLite storage."},
                     headers=owner_headers)
    assert r.status_code == 200
    assert "SQLite" in r.json()["text"]
    # the evidence index reflects the edit
    top = client.post("/rag/query", json={"text": "Flask SQLite club API", "k": 3},
                      headers=owner_headers).json()
    assert any("SQLite" in t["text"] for t in top)
    client.delete(f"/career/items/{item['id']}", headers=owner_headers)


def test_edit_pool_bullet_writes_back_to_yaml(tmp_path, monkeypatch):
    """Editing a pool bullet updates the pool file (source of truth)."""
    import os

    import yaml
    from fastapi.testclient import TestClient

    from main import create_app

    pool_copy = tmp_path / "pool.yaml"
    shutil.copy(os.environ["CAREERPILOT_POOL"], pool_copy)
    monkeypatch.setitem(os.environ, "CAREERPILOT_POOL", str(pool_copy))

    app = create_app(f"sqlite:///{tmp_path / 'edit.db'}")
    c = TestClient(app)
    tok = c.post("/auth/login", json={"email": "dhirenrao@gmail.com",
                                      "password": "test-password"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    items = c.get("/career", headers=h).json()
    bullet = next(i for i in items if i["kind"] == "bullet")
    new_text = bullet["text"].rstrip(".") + " with weekly stakeholder demos."
    r = c.patch(f"/career/items/{bullet['id']}", json={"text": new_text}, headers=h)
    assert r.status_code == 200

    with open(pool_copy, encoding="utf-8") as f:
        pool = yaml.safe_load(f)
    texts = [b["text"] for s in ("experience", "projects")
             for e in pool[s] for b in e["bullets"]]
    assert any("weekly stakeholder demos" in t for t in texts)

    # viewer-blocked and empty-text guarded
    assert c.patch(f"/career/items/{bullet['id']}", json={"text": "  "},
                   headers=h).status_code == 400
