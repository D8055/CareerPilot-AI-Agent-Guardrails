"""Password rules: startup NEVER silently changes an existing owner's
password (even with the env var set — that was a real lockout footgun);
the explicit reset script is the only way it changes."""
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))


def test_startup_never_resets_existing_owner(tmp_path, monkeypatch):
    from main import create_app
    db_url = f"sqlite:///{tmp_path / 'reset.db'}"

    monkeypatch.setitem(os.environ, "CAREERPILOT_OWNER_PASSWORD", "first-pw")
    create_app(db_url)

    # a second start with a DIFFERENT env password must NOT change anything
    monkeypatch.setitem(os.environ, "CAREERPILOT_OWNER_PASSWORD", "attacker-or-typo")
    client = TestClient(create_app(db_url))
    assert client.post("/auth/login", json={
        "email": "dhirenrao@gmail.com", "password": "first-pw"}).status_code == 200
    assert client.post("/auth/login", json={
        "email": "dhirenrao@gmail.com", "password": "attacker-or-typo"}).status_code == 401


def test_explicit_reset_script_changes_password(tmp_path, monkeypatch):
    import reset_password
    from main import create_app
    db_url = f"sqlite:///{tmp_path / 'reset2.db'}"

    monkeypatch.setitem(os.environ, "CAREERPILOT_OWNER_PASSWORD", "first-pw")
    app = create_app(db_url)

    monkeypatch.setitem(os.environ, "DATABASE_URL", db_url)
    email = reset_password.reset("TestPassword")
    assert email == "dhirenrao@gmail.com"

    client = TestClient(app)
    assert client.post("/auth/login", json={
        "email": email, "password": "TestPassword"}).status_code == 200
    assert client.post("/auth/login", json={
        "email": email, "password": "first-pw"}).status_code == 401
