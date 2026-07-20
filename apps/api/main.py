"""CareerPilot core API — Phase 0 slice.

Deterministic and keyless by design: every endpoint works with no LLM, no API
key, and no network. Intelligence quality passes arrive in Phase 1 via the
local runner (Claude Agent SDK on the owner's subscription) — see docs/careerpilot-spec.md.
"""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from careerpilot_shared import (build_pool_plan, extract_jd_terms, load_pool,
                                match_score, validate_pool_plan)
from careerpilot_shared.models import TailorReport, TailorRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POOL = REPO_ROOT / "data" / "demo_career_pool.yaml"

app = FastAPI(
    title="CareerPilot API",
    description="Job search copilot with a hard honesty boundary: "
                "tailoring SELECTS from a verified career pool, never invents.",
)


def get_pool() -> dict:
    return load_pool(os.environ.get("CAREERPILOT_POOL", DEFAULT_POOL))


@app.get("/health")
def health() -> dict:
    pool = get_pool()
    return {"status": "ok", "pool_bullets": sum(
        len(e["bullets"]) for s in ("experience", "projects") for e in pool[s])}


@app.post("/tailor", response_model=TailorReport)
def tailor(req: TailorRequest) -> TailorReport:
    """Deterministic tailor: JD analysis + selection plan, honesty enforced."""
    pool = get_pool()
    matched, missing = extract_jd_terms(req.jd_text, pool)
    summary = (pool.get("meta") or {}).get("fallback_summary")
    if not summary:
        raise HTTPException(500, "pool has no fallback_summary")
    plan = build_pool_plan(pool, matched, summary_text=summary)
    violations = validate_pool_plan(pool, plan)
    if violations:
        raise HTTPException(500, f"deterministic plan failed validation: {violations}")
    return TailorReport(
        match_score=match_score(matched, missing),
        matched_keywords=matched,
        missing_keywords=missing,
        plan=plan,
    )
