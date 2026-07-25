"""Runner quality-pass graph: the three-stage recruiter review (analyze →
rewrite → ATS), with an injected fake LLM (no SDK, no network)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "runner"))

pytest.importorskip("langgraph")
from graph import run_quality_pass  # noqa: E402

EVIDENCE = [{"text": "Built a Python scraping platform that cut manual data "
                     "collection 96% across government and nonprofit sites."}]
BASELINE = "Computer science student building data driven software in Python."
BULLETS = ["Cut manual data collection 96% with a Python web scraper."]


def scripted_llm(responses: list[str]):
    calls = iter(responses)
    seen = []

    def llm(prompt: str, system: str) -> str:
        seen.append((system, prompt))
        return next(calls)
    llm.seen = seen
    return llm


def test_three_stage_flow_returns_all_parts():
    llm = scripted_llm([
        "Match 72/100. Missing: Kafka, Spring. Red flags: no Java role.",  # analyze
        "SUMMARY: Cut data collection 96% with a Python scraper.\n"
        "EXPERIENCE:\n- Accomplished a 96% cut in manual collection by "
        "building a Python scraper.",                                       # rewrite
        "The skills section would get skipped; tightened it.",             # ats
    ])
    out = run_quality_pass(llm, "Scale AI", "Python automation role",
                           EVIDENCE, BASELINE, baseline_bullets=BULLETS,
                           missing_keywords=["kafka", "spring"])
    assert "72/100" in out["analysis"]
    assert "96%" in out["summary_text"]
    assert "Accomplished" in out["rewritten_experience"]
    assert "skipped" in out["ats_notes"]


def test_stage1_prompt_names_the_company_and_asks_for_score():
    llm = scripted_llm(["score", "SUMMARY: s\nEXPERIENCE:\n- b", "ats"])
    run_quality_pass(llm, "BeaconFire", "jd", EVIDENCE, BASELINE)
    system, prompt = llm.seen[0]
    assert "BeaconFire" in system
    assert "match score out of 100" in prompt
    assert "red flags" in prompt


def test_rewrite_prompt_forbids_invented_keywords():
    llm = scripted_llm(["score", "SUMMARY: s\nEXPERIENCE:\n- b", "ats"])
    run_quality_pass(llm, "Co", "jd", EVIDENCE, BASELINE,
                     missing_keywords=["kafka"])
    _, rewrite_prompt = llm.seen[1]
    assert "not in the evidence" in rewrite_prompt.lower() or \
           "leave it out" in rewrite_prompt.lower()
    assert "XYZ" in rewrite_prompt or "Accomplished X" in rewrite_prompt


def test_llm_failure_reports_error():
    def broken(prompt, system):
        raise RuntimeError("SDK unavailable")
    out = run_quality_pass(broken, "Co", "jd", EVIDENCE, BASELINE)
    assert "error" in out
