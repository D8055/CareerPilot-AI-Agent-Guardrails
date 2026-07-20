"""Runner quality-pass graph: review loop, refutation, and error handling —
all with an injected fake LLM (no SDK, no network, fully deterministic)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "runner"))

pytest.importorskip("langgraph")
from graph import run_quality_pass  # noqa: E402

EVIDENCE = [{"text": "Built a Python scraping platform that cut manual data "
                     "collection 90% across three source sites."}]
BASELINE = "Computer science student building data driven software in Python."


def scripted_llm(responses: list[str]):
    calls = iter(responses)

    def llm(prompt: str, system: str) -> str:
        return next(calls)
    return llm


def test_grounded_first_try():
    llm = scripted_llm(["Student who cut manual data collection 90% with a "
                        "Python scraping platform.", "GROUNDED"])
    out = run_quality_pass(llm, "Python automation role", EVIDENCE, BASELINE)
    assert "summary_text" in out and "90%" in out["summary_text"]


def test_refutation_loops_then_accepts():
    llm = scripted_llm([
        "Kubernetes expert with 500% gains.",          # tailor 1 (fabricated)
        "- Kubernetes is not in the evidence",         # review 1: refuted
        "Cut manual data collection 90% with Python.",  # tailor 2 (grounded)
        "GROUNDED",                                    # review 2
    ])
    out = run_quality_pass(llm, "Python automation role", EVIDENCE, BASELINE)
    assert "summary_text" in out and "Kubernetes" not in out["summary_text"]


def test_persistent_refutation_keeps_deterministic():
    llm = scripted_llm([
        "Fabrication one.", "- ungrounded claim A",
        "Fabrication two.", "- ungrounded claim B",
    ])
    out = run_quality_pass(llm, "role", EVIDENCE, BASELINE)
    assert "summary_text" not in out and "refuted" in out


def test_llm_failure_reports_error():
    def broken(prompt, system):
        raise RuntimeError("SDK unavailable")
    out = run_quality_pass(broken, "role", EVIDENCE, BASELINE)
    assert "error" in out
