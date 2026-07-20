"""JD term split and match scoring (ported from the applier's suite)."""
from careerpilot_shared import extract_jd_terms, match_score

JD = """We're hiring a Software Engineering Intern. You'll build React frontends and
.NET services on Azure, write SQL, and ship through CI/CD. Experience with
Kubernetes and Terraform is a plus. Python scripting for data pipelines welcome."""


def test_jd_terms_split_matched_vs_missing(pool):
    matched, missing = extract_jd_terms(JD, pool)
    assert "react" in matched and ".net" in matched and "azure" in matched
    assert "kubernetes" in missing and "terraform" in missing
    # missing keywords are flagged, never claimed — they must not be in the pool
    for term in missing:
        assert not any(term in i.lower() for g in pool["skills"] for i in g["items"])
    score = match_score(matched, missing)
    assert 0 < score < 100


def test_match_score_empty_jd():
    assert match_score([], []) is None
