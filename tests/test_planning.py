"""Plan building and selection-only validation (ported from the applier)."""
import copy

from careerpilot_shared import build_pool_plan, extract_jd_terms, validate_pool_plan

JD = """Full stack developer for REST microservices with React frontends, SQL,
CI/CD, and AI integration (RAG, LLM extraction). PostgreSQL welcome."""


def _plan(pool):
    matched, _ = extract_jd_terms(JD, pool)
    return build_pool_plan(pool, matched,
                           summary_text=pool["meta"]["fallback_summary"])


def test_pool_shape(pool):
    assert len(pool["projects"]) >= 4   # over-complete by design; tailor picks 3
    for role in pool["experience"]:
        assert role["select"]["min"] <= role["select"]["max"] <= len(role["bullets"])


def test_deterministic_pool_plan_validates(pool):
    assert validate_pool_plan(pool, _plan(pool)) == []


def test_validate_rejects_bad_selections(pool):
    base = _plan(pool)
    p = copy.deepcopy(base)
    p["experience"][0]["bullets"] = p["experience"][0]["bullets"][:1]  # below min
    assert any("bullets" in v for v in validate_pool_plan(pool, p))
    p = copy.deepcopy(base)
    p["experience"][0]["bullets"][0] = "not-a-real-id"
    assert any("unknown bullet" in v for v in validate_pool_plan(pool, p))
    p = copy.deepcopy(base)
    p["projects"] = p["projects"][:2]                                  # not 3
    assert any("exactly 3" in v for v in validate_pool_plan(pool, p))
    p = copy.deepcopy(base)
    p["skills"][0]["items"] = p["skills"][0]["items"] + ["Kubernetes"]  # addition
    assert any("not in the pool" in v for v in validate_pool_plan(pool, p))
    p = copy.deepcopy(base)
    p["summary_text"] = ("Student with 320% Kubernetes gains and deep Terraform "
                         "expertise across production fleets and many large "
                         "scale distributed systems everywhere always and more.")
    assert validate_pool_plan(pool, p)                                 # honesty
