"""The LangGraph quality-pass graph — a three-stage recruiter review.

Stage 1 (analyze): act as a senior recruiter for the exact company; score the
resume, name missing keywords and the red flags a hiring manager spots fast.
Stage 2 (rewrite): rewrite experience with the Google XYZ formula, weaving in
the keywords the candidate TRULY has and removing red flags.
Stage 3 (ats): act as an ATS filter and a hiring manager reading 200 resumes;
flag skippable sections and rewrite them to stop the scroll.

Honesty boundary (non-negotiable, enforced in code, not by prompt): the API's
check_honesty + validate_pool_plan re-validate everything this graph proposes.
Missing keywords the record cannot back are NEVER written in — they are routed
to the confirmation-question flow for the owner. LLM proposes, code disposes,
human confirms.
"""
from typing import TypedDict

from langgraph.graph import END, StateGraph

# Condensed from the humanizer skill (Wikipedia "Signs of AI writing"): the
# output must not read as AI-generated.
HUMANIZER_RULES = (
    "Write like a human, not an AI. No em dashes or en dashes. No hyphens in "
    "descriptions. Avoid AI-tell vocabulary (leverage, spearheaded, "
    "tapestry, testament, showcase, underscore, robust, seamless, pivotal). "
    "Vary sentence length. Prefer concrete specifics over promotional "
    "adjectives. No rule-of-three lists, no 'not just X but Y' constructions, "
    "no filler or hedging. Plain, direct, active voice."
)

FORMAT_RULES = (
    "Match the candidate's existing resume format exactly: same section order, "
    "same concise one-line bullet style, past-tense action verbs, no personal "
    "pronouns, no headers or labels inside a bullet."
)

XYZ = ("Google XYZ formula: 'Accomplished X as measured by Y by doing Z' — lead "
       "with the accomplishment, quantify it with the metric already in the "
       "evidence, then name what was done. Keep every number and technology "
       "exactly as it appears in the evidence; invent nothing.")


class QualityState(TypedDict, total=False):
    company: str
    jd_text: str
    evidence: list[dict]         # top-k career items from /rag/query
    baseline_summary: str        # the deterministic summary already live
    baseline_bullets: list[str]  # the selected experience bullets, verbatim
    missing_keywords: list[str]  # flagged; NOT claimable unless confirmed
    analysis: str                # stage 1 output
    rewritten_summary: str       # stage 2 output (guarded before use)
    rewritten_experience: str    # stage 2 output (proposal for owner review)
    ats_notes: str               # stage 3 output
    error: str


def _evidence_block(state: QualityState) -> str:
    return "\n".join(f"- {e['text']}" for e in state.get("evidence", []))


def make_graph(llm):
    """llm: callable (prompt, system) -> str. Injected so tests run without the
    Claude Agent SDK and the SDK wrapper stays one line to swap."""

    # ---- stage 1: recruiter analysis ----
    def analyze(state: QualityState) -> QualityState:
        system = (
            f"Act as a senior technical recruiter for {state.get('company') or 'this company'}. "
            "You screen candidates for this exact role every day. Be blunt and specific."
        )
        prompt = (
            f"Job description:\n{state['jd_text'][:4000]}\n\n"
            f"Candidate's verified resume evidence:\n{_evidence_block(state)}\n"
            f"Current summary: {state['baseline_summary']}\n\n"
            "Analyze this resume against this job description and give me:\n"
            "1. A match score out of 100.\n"
            "2. The top 5 missing keywords.\n"
            "3. The 3 red flags a hiring manager would spot in under 10 seconds.\n\n"
            "Start your reply with a single line 'SCORE: N' where N is the match "
            "score as an integer from 0 to 100, then the rest of the analysis."
        )
        try:
            return {**state, "analysis": llm(prompt, system).strip()}
        except Exception as e:
            return {**state, "error": str(e)}

    # ---- stage 2: XYZ rewrite (honesty-bounded) ----
    def rewrite(state: QualityState) -> QualityState:
        if state.get("error"):
            return state
        system = (
            "You rewrite resume bullets and summaries. " + HUMANIZER_RULES + " " + FORMAT_RULES
        )
        prompt = (
            f"Job description:\n{state['jd_text'][:3000]}\n\n"
            f"Recruiter analysis:\n{state.get('analysis', '')}\n\n"
            "Verified evidence (the ONLY facts you may use — every number and "
            f"technology must already appear here):\n{_evidence_block(state)}\n\n"
            "Current summary:\n" + state["baseline_summary"] + "\n\n"
            "Current experience bullets:\n"
            + "\n".join(f"- {b}" for b in state.get("baseline_bullets", [])) + "\n\n"
            "Rewrite my summary and experience section to naturally include the "
            "keywords I TRULY have from the evidence and to remove the red flags. "
            "Do NOT add any skill, tool, number, or keyword that is not in the "
            "evidence above; if a keyword is missing from my evidence, leave it "
            "out. " + XYZ + "\n\n"
            "Return the rewritten summary first under a line 'SUMMARY:', then the "
            "rewritten bullets under a line 'EXPERIENCE:', one bullet per line."
        )
        try:
            out = llm(prompt, system).strip()
        except Exception as e:
            return {**state, "error": str(e)}
        summary, experience = _split_rewrite(out)
        return {**state, "rewritten_summary": summary, "rewritten_experience": experience}

    # ---- stage 3: ATS + hiring-manager scan ----
    def ats(state: QualityState) -> QualityState:
        if state.get("error"):
            return state
        system = (
            "You are both an ATS keyword filter and a hiring manager reading 200 "
            "resumes in one sitting. " + HUMANIZER_RULES + " " + FORMAT_RULES
        )
        prompt = (
            f"Job description:\n{state['jd_text'][:3000]}\n\n"
            "My rewritten resume:\n"
            f"SUMMARY: {state.get('rewritten_summary', state['baseline_summary'])}\n"
            f"EXPERIENCE:\n{state.get('rewritten_experience', '')}\n\n"
            "Scan my new resume as an ATS and as a hiring manager. Tell me which "
            "sections would get skipped, then rewrite those sections so they stop "
            "the scroll. Keep every number and technology exactly as written; add "
            "nothing that is not already there."
        )
        try:
            return {**state, "ats_notes": llm(prompt, system).strip()}
        except Exception as e:
            return {**state, "error": str(e)}

    g = StateGraph(QualityState)
    g.add_node("analyze", analyze)
    g.add_node("rewrite", rewrite)
    g.add_node("ats", ats)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "rewrite")
    g.add_edge("rewrite", "ats")
    g.add_edge("ats", END)
    return g.compile()


def _split_rewrite(text: str) -> tuple[str, str]:
    """Parse the SUMMARY: / EXPERIENCE: sections from stage 2 output."""
    summary, experience, mode = [], [], None
    for line in text.splitlines():
        up = line.strip().upper()
        if up.startswith("SUMMARY:"):
            mode = "s"
            rest = line.split(":", 1)[1].strip()
            if rest:
                summary.append(rest)
        elif up.startswith("EXPERIENCE:"):
            mode = "e"
            rest = line.split(":", 1)[1].strip()
            if rest:
                experience.append(rest)
        elif mode == "s":
            summary.append(line.strip())
        elif mode == "e":
            experience.append(line.strip())
    return " ".join(x for x in summary if x).strip(), \
        "\n".join(x for x in experience if x).strip()


def run_quality_pass(llm, company: str, jd_text: str, evidence: list[dict],
                     baseline_summary: str,
                     baseline_bullets: list[str] | None = None,
                     missing_keywords: list[str] | None = None) -> dict:
    """Run the three-stage recruiter review. Returns the analysis, the proposed
    rewrites, and the ATS notes. The caller (API) runs the honesty guard on the
    rewritten summary before anything is committed; the rest is surfaced for the
    owner to review."""
    graph = make_graph(llm)
    out: QualityState = graph.invoke({
        "company": company, "jd_text": jd_text, "evidence": evidence,
        "baseline_summary": baseline_summary,
        "baseline_bullets": baseline_bullets or [],
        "missing_keywords": missing_keywords or [],
    })
    if out.get("error"):
        return {"error": out["error"]}
    return {
        "analysis": out.get("analysis", ""),
        "llm_match": _parse_score(out.get("analysis", "")),
        "summary_text": out.get("rewritten_summary", ""),
        "rewritten_experience": out.get("rewritten_experience", ""),
        "ats_notes": out.get("ats_notes", ""),
    }


def _parse_score(analysis: str) -> int | None:
    """Pull the recruiter's 0-100 match score from the analysis text."""
    import re
    m = re.search(r"SCORE:\s*(\d{1,3})", analysis, re.I)
    if not m:
        m = re.search(r"(\d{1,3})\s*/\s*100", analysis)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM reply (tolerates fences)."""
    import json
    import re
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        out = json.loads(text[start:end + 1])
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def run_full_tailor(llm, company: str, jd_text: str, menu: dict,
                    confirmations: str = "", validate=None) -> dict:
    """Purely-AI tailoring: Claude analyzes the JD as a recruiter (score,
    gaps, red flags), then authors the COMPLETE plan — which bullets, which
    projects, skills order, and the summary — selecting only from the menu.
    The API's validator is the final gate on whatever comes back."""
    import json

    system = (
        f"Act as a senior technical recruiter for {company or 'this company'} "
        "who also writes resumes. " + HUMANIZER_RULES
    )
    analyze_prompt = (
        f"Job description:\n{jd_text[:4000]}\n\n"
        "Candidate's verified content menu (JSON):\n"
        + json.dumps(menu, indent=1)[:9000] + "\n\n"
        + (f"Owner-confirmed extras: {confirmations[:800]}\n\n" if confirmations else "")
        + "Analyze the candidate against this job description and give me:\n"
          "1. A match score out of 100.\n"
          "2. The top 5 missing keywords.\n"
          "3. The 3 red flags a hiring manager would spot in under 10 seconds.\n\n"
          "Start with a single line 'SCORE: N' (integer 0-100), then the analysis."
    )
    try:
        analysis = llm(analyze_prompt, system).strip()
    except Exception as e:
        return {"error": str(e)}

    plan_prompt = (
        f"Job description:\n{jd_text[:3500]}\n\n"
        f"Your recruiter analysis:\n{analysis[:2000]}\n\n"
        "Verified content menu (you may ONLY select ids and reorder items "
        "from it; every fact in your summary must appear in it):\n"
        + json.dumps(menu, indent=1)[:9000] + "\n\n"
        "Author the tailored resume plan for this job:\n"
        "- For EVERY experience role (keep menu order): pick the bullets that "
        "best sell this candidate for THIS job, within select_min..select_max.\n"
        "- Pick exactly 3 projects, each with bullets within its bounds.\n"
        "- Reorder every skills group so JD-relevant items lead (keep all "
        "items, same groups, same order of groups).\n"
        "- Write summary_text (25-80 words) per the menu's summary_rules. "
        + XYZ + "\n\n"
        "Output ONLY this JSON, nothing else:\n"
        '{"summary_text": "...", "summary_bold": "", '
        '"skills": [{"label": "...", "items": ["..."]}], '
        '"experience": [{"id": "...", "bullets": ["bullet-id", "..."]}], '
        '"projects": [{"id": "...", "bullets": ["bullet-id", "..."]}]}'
    )
    try:
        raw = llm(plan_prompt, system)
    except Exception as e:
        return {"error": str(e)}
    plan = _extract_json(raw)
    if not plan:
        return {"error": "AI tailor returned unparseable plan JSON"}

    # repair loop: the validator's exact complaints go back to Claude
    # (ONE round — each round is a full plan-priced call). The repair prompt
    # deliberately omits the big menu; the plan + violations carry enough.
    if validate is not None:
        for _ in range(1):
            violations = validate(plan)
            if not violations:
                break
            repair_prompt = (
                "Your resume plan was rejected by the validator for these "
                "exact reasons:\n- " + "\n- ".join(str(v) for v in violations)
                + "\n\nHere is the plan you produced:\n" + json.dumps(plan)
                + "\n\nRules: select ids only (they must come from the plan "
                "you already saw the menu for), ALL experience roles in the "
                "original order, EXACTLY 3 distinct projects, bullet counts "
                "within each select_min..select_max, every skills group "
                "present in original group order (reorder items inside "
                "only), summary 25-80 words using only facts you already "
                "used. Return ONLY the corrected JSON, nothing else."
            )
            try:
                raw = llm(repair_prompt, system)
            except Exception as e:
                return {"error": str(e)}
            fixed = _extract_json(raw)
            if fixed:
                plan = fixed
    return {"plan": plan, "analysis": analysis,
            "llm_match": _parse_score(analysis)}
