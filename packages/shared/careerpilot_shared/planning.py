"""Tailor plans: deterministic selection from the pool, and strict validation.

A plan may SELECT and ORDER pool content and write the summary — nothing else.
"""
from .analysis import norm_term, term_in
from .honesty import check_honesty


def _bullet_score(bullet: dict, jd_terms: set[str]) -> int:
    text = norm_term(bullet["text"] + " " + " ".join(bullet.get("keywords", [])))
    return sum(1 for t in jd_terms if term_in(t, text))


def build_pool_plan(pool: dict, jd_terms: list[str],
                    summary_text: str | None = None) -> dict:
    """Deterministic selection: per role, the top-scoring bullets up to the
    role's select.max; the 3 best projects with their top bullets; skills
    reordered JD-relevant-first (all items kept)."""
    terms = set(jd_terms)

    def top(bullets, n):
        ranked = sorted(bullets, key=lambda b: -_bullet_score(b, terms))
        return [b["id"] for b in ranked[:n]]

    proj_ranked = sorted(
        pool["projects"],
        key=lambda pj: -sum(_bullet_score(b, terms) for b in pj["bullets"]))[:3]
    return {
        "summary_text": summary_text or "",
        "summary_bold": "",
        "skills": [{"label": g["label"],
                    "items": sorted(g["items"],
                                    key=lambda i: 0 if term_in(norm_term(i),
                                                               " ".join(terms)) else 1)}
                   for g in pool["skills"]],
        "experience": [{"id": r["id"],
                        "bullets": top(r["bullets"], r["select"]["max"])}
                       for r in pool["experience"]],
        "projects": [{"id": pj["id"],
                      "bullets": top(pj["bullets"], pj["select"]["max"])}
                     for pj in proj_ranked],
    }


def validate_pool_plan(pool: dict, plan: dict, extra_corpus: str = "") -> list[str]:
    """Selection counts must respect each role's select bounds; the summary must
    pass the honesty guard. Empty list = valid."""
    v = []
    words = len(str(plan.get("summary_text", "")).split())
    if not 25 <= words <= 80:
        v.append(f"summary length {words} words (want 25-80)")
    v += check_honesty(str(plan.get("summary_text", "")), pool, extra_corpus)
    bold = plan.get("summary_bold") or ""
    if bold and bold not in plan.get("summary_text", ""):
        v.append("summary_bold is not a substring of summary_text")

    if [e.get("id") for e in plan.get("experience", [])] != \
            [r["id"] for r in pool["experience"]]:
        v.append("experience roles must appear exactly in pool order")
    else:
        for entry, role in zip(plan["experience"], pool["experience"]):
            ids = entry.get("bullets", [])
            known = {b["id"] for b in role["bullets"]}
            sel = role.get("select", {"min": 1, "max": len(known)})
            if len(ids) != len(set(ids)):
                v.append(f"role {role['id']}: duplicate bullets")
            if not set(ids) <= known:
                v.append(f"role {role['id']}: unknown bullet ids {set(ids) - known}")
            if not sel["min"] <= len(ids) <= sel["max"]:
                v.append(f"role {role['id']}: {len(ids)} bullets "
                         f"(want {sel['min']}-{sel['max']})")

    pj_by_id = {pj["id"]: pj for pj in pool["projects"]}
    got = [e.get("id") for e in plan.get("projects", [])]
    if len(got) != 3 or len(set(got)) != 3 or not set(got) <= set(pj_by_id):
        v.append("projects: select exactly 3 distinct pool project ids")
    else:
        for entry in plan["projects"]:
            pj = pj_by_id[entry["id"]]
            known = {b["id"] for b in pj["bullets"]}
            sel = pj.get("select", {"min": 2, "max": 2})
            ids = entry.get("bullets", [])
            if not set(ids) <= known or len(ids) != len(set(ids)) \
                    or not sel["min"] <= len(ids) <= sel["max"]:
                v.append(f"project {entry['id']}: bullet selection invalid")

    if [g.get("label") for g in plan.get("skills", [])] != \
            [g["label"] for g in pool["skills"]]:
        v.append("skills groups must appear exactly in pool order")
    else:
        for got_g, src in zip(plan["skills"], pool["skills"]):
            items = got_g.get("items", [])
            if not set(items) <= set(src["items"]):
                v.append(f"skills '{src['label']}': items not in the pool: "
                         f"{set(items) - set(src['items'])}")
            if len(items) < min(5, len(src["items"])):
                v.append(f"skills '{src['label']}': too few items ({len(items)})")
            if len(items) != len(set(items)):
                v.append(f"skills '{src['label']}': duplicates")
    return v
