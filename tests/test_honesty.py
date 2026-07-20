"""The honesty guard: no number or tech term the pool cannot back (ported)."""
from careerpilot_shared import check_honesty


def test_honesty_guard_accepts_verified_summary(pool):
    assert check_honesty(pool["meta"]["fallback_summary"], pool) == []


def test_honesty_guard_rejects_fabrications(pool):
    bad_term = check_honesty("Built services with Kubernetes on Azure.", pool)
    assert any("kubernetes" in v.lower() for v in bad_term)
    bad_num = check_honesty("Improved throughput 320% in Python.", pool)
    assert any("320%" in v for v in bad_num)
    bad_dash = check_honesty("Software — built fast.", pool)
    assert any("em dash" in v for v in bad_dash)
