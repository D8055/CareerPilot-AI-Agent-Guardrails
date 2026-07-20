"""Career pool loading. Tier-1/confirmed content only, over-complete by design:
tailor plans SELECT from it, bullet text renders verbatim."""
from pathlib import Path

import yaml

REQUIRED_SECTIONS = ("contact", "experience", "projects", "skills", "accomplishments")


class PoolError(Exception):
    pass


def load_pool(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        pool = yaml.safe_load(f)
    for key in REQUIRED_SECTIONS:
        if key not in pool:
            raise PoolError(f"career pool missing section: {key}")
    return pool
