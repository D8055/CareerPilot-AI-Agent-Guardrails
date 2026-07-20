"""CareerPilot shared core: career pool, JD analysis, honesty guard, tailoring.

Ported from the InternshipApplier's proven engine (105 tests). The honesty
boundary is the whole point: plans SELECT verified content, never invent it.
"""
from .analysis import extract_jd_terms, master_corpus, match_score
from .honesty import check_honesty
from .planning import build_pool_plan, validate_pool_plan
from .pool import PoolError, load_pool

__all__ = [
    "extract_jd_terms", "master_corpus", "match_score", "check_honesty",
    "build_pool_plan", "validate_pool_plan", "PoolError", "load_pool",
]
