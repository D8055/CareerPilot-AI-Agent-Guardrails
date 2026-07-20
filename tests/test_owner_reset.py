"""CAREERPILOT_OWNER_PASSWORD must always win, even on an existing database —
a forgotten first-start password must never lock the owner out."""
import os

from fastapi.testclient import TestClient


def test_env_password_resets_existing_owner(tmp_path, monkeypatch):
    from main import create_app
    db_url = f"sqlite:///{tmp_path / 'reset.db'}"

    monkeypatch.setitem(os.environ, "CAREERPILOT_OWNER_PASSWORD", "first-pw")
    create_app(db_url)

    monkeypatch.setitem(os.environ, "CAREERPILOT_OWNER_PASSWORD", "TestPassword")
    client = TestClient(create_app(db_url))

    assert client.post("/auth/login", json={
        "email": "dhirenrao@gmail.com", "password": "first-pw"}).status_code == 401
    r = client.post("/auth/login", json={
        "email": "dhirenrao@gmail.com", "password": "TestPassword"})
    assert r.status_code == 200 and r.json()["role"] == "owner"
