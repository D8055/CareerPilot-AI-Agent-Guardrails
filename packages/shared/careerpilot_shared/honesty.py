"""The honesty guard: LLM proposes, this code disposes."""
import re

from .analysis import master_corpus, norm_term, term_in
from .lexicon import TECH_LEXICON


def check_honesty(candidate: str, pool: dict, extra_corpus: str = "") -> list[str]:
    """Violations in generated text: any number or tech term not in the
    verified content (pool + owner confirmations), or an em dash (banned by
    the resume rules). Empty list = clean."""
    violations = []
    corpus = master_corpus(pool) + " " + norm_term(extra_corpus)
    cand = norm_term(candidate)
    if "—" in candidate:
        violations.append("em dash in generated text")
    for num in set(re.findall(r"~?\d[\d,.]*%?\+?", cand)):
        if num not in corpus:
            violations.append(f"number not in master: {num}")
    for term in TECH_LEXICON:
        t = norm_term(term)
        if term_in(t, cand) and not term_in(t, corpus):
            violations.append(f"term not in master: {term}")
    return violations
