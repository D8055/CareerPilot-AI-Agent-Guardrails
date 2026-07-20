import os
import sys
from pathlib import Path

import pytest

from careerpilot_shared import load_pool

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

os.environ.setdefault("CAREERPILOT_OWNER_PASSWORD", "test-password")
os.environ.setdefault("CAREERPILOT_JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")


@pytest.fixture(scope="session")
def pool() -> dict:
    return load_pool(REPO_ROOT / "data" / "demo_career_pool.yaml")


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient

    from main import create_app
    db = tmp_path_factory.mktemp("db") / "test.db"
    app = create_app(f"sqlite:///{db}")
    return TestClient(app)


@pytest.fixture(scope="session")
def owner_headers(client) -> dict:
    r = client.post("/auth/login", json={"email": "dhirenrao@gmail.com",
                                         "password": "test-password"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def viewer_headers(client, owner_headers) -> dict:
    tok = client.post("/auth/share", headers=owner_headers).json()["viewer_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def runner_headers() -> dict:
    return {"X-Runner-Token": "dev-local-runner", "X-Runner-Id": "test-runner"}
