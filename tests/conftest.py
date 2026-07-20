from pathlib import Path

import pytest

from careerpilot_shared import load_pool

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def pool() -> dict:
    return load_pool(REPO_ROOT / "data" / "demo_career_pool.yaml")
