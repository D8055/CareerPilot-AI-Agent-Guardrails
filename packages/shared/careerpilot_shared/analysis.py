"""JD analysis: which posting terms the verified pool can truthfully claim."""
import re

from .lexicon import TECH_LEXICON


def norm_term(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def term_in(term: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def master_corpus(pool: dict) -> str:
    """Every piece of verified text, lowercased — the honesty-guard haystack."""
    parts = []
    if "summary" in pool:
        parts.append(pool["summary"]["text"])
    meta = pool.get("meta") or {}
    parts.append(meta.get("fallback_summary", ""))
    for g in pool["skills"]:
        parts.append(g["label"] + " " + ", ".join(g["items"]))
    for section in ("experience", "projects"):
        for entry in pool[section]:
            parts.append(entry.get("org", "") + " " + entry.get("title", "") +
                         " " + entry.get("name", "") + " " + entry.get("stack", ""))
            for b in entry["bullets"]:
                parts.append(b["text"] + " " + " ".join(b.get("keywords", [])))
    for a in pool["accomplishments"]:
        parts.append(a["text"] + " " + " ".join(a.get("keywords", [])))
    return norm_term(" ".join(parts))


def extract_jd_terms(jd_text: str, pool: dict) -> tuple[list[str], list[str]]:
    """(matched, missing): lexicon+pool terms found in the JD, split by whether
    the verified pool can truthfully claim them."""
    jd = norm_term(jd_text)
    corpus = master_corpus(pool)
    pool_terms = set()
    for g in pool["skills"]:
        pool_terms.update(norm_term(i) for i in g["items"])
    for section in ("experience", "projects"):
        for entry in pool[section]:
            for b in entry["bullets"]:
                pool_terms.update(norm_term(k) for k in b.get("keywords", []))
    vocab = sorted(set(norm_term(t) for t in TECH_LEXICON) | pool_terms)
    matched, missing = [], []
    for term in vocab:
        if len(term) < 2 or not term_in(term, jd):
            continue
        (matched if term_in(term, corpus) else missing).append(term)
    return matched, missing


def match_score(matched: list[str], missing: list[str]) -> int | None:
    total = len(matched) + len(missing)
    return round(100 * len(matched) / total) if total else None
