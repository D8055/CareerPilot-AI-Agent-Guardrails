"""The LangGraph quality-pass graph.

State machine per spec §2.3: retrieve evidence → tailor (LLM proposes a
sharper summary bounded by that evidence) → review (adversarial refutation)
→ loop back once on refutation → finish. The API's honesty guard is the
final, non-negotiable gate on whatever leaves this graph.
"""
from typing import TypedDict

from langgraph.graph import END, StateGraph

MAX_REVIEW_LOOPS = 2

TAILOR_SYSTEM = (
    "You tighten resume summaries. You may ONLY use facts present in the "
    "provided evidence — no new numbers, no new technologies, no em dashes, "
    "no hyphens. 25-80 words, one paragraph, plain text only."
)

REVIEW_SYSTEM = (
    "You are an adversarial reviewer. Refute any claim in the candidate "
    "summary that is not directly grounded in the evidence. Reply with "
    "exactly 'GROUNDED' if every claim is backed, otherwise list the "
    "ungrounded claims, one per line."
)


class QualityState(TypedDict, total=False):
    jd_text: str
    evidence: list[dict]        # top-k career items from /rag/query
    baseline_summary: str       # the deterministic summary already live
    proposal: str
    verdict: str
    loops: int
    error: str


def _evidence_block(state: QualityState) -> str:
    return "\n".join(f"- {e['text']}" for e in state.get("evidence", []))


def make_graph(llm):
    """llm: callable (prompt, system) -> str. Injected so tests run without
    the SDK and the SDK wrapper stays one line to swap."""

    def tailor(state: QualityState) -> QualityState:
        prompt = (
            f"Job description:\n{state['jd_text'][:4000]}\n\n"
            f"Verified evidence (the ONLY permitted facts):\n{_evidence_block(state)}\n\n"
            f"Current summary:\n{state['baseline_summary']}\n\n"
            "Rewrite the summary to better address this job description. "
            "Same facts, sharper emphasis. Output ONLY the summary text."
        )
        if state.get("verdict") and state["verdict"] != "GROUNDED":
            prompt += ("\n\nYour previous attempt was refuted:\n"
                       f"{state['verdict']}\nRemove or replace those claims.")
        try:
            proposal = llm(prompt, TAILOR_SYSTEM)
        except Exception as e:
            return {**state, "error": str(e)}
        return {**state, "proposal": proposal.strip(),
                "loops": state.get("loops", 0) + 1}

    def review(state: QualityState) -> QualityState:
        if state.get("error"):
            return state
        prompt = (f"Evidence:\n{_evidence_block(state)}\n\n"
                  f"Candidate summary:\n{state['proposal']}")
        try:
            verdict = llm(prompt, REVIEW_SYSTEM)
        except Exception as e:
            return {**state, "error": str(e)}
        return {**state, "verdict": verdict.strip()}

    def route(state: QualityState) -> str:
        if state.get("error"):
            return "done"
        if state.get("verdict", "").upper().startswith("GROUNDED"):
            return "done"
        if state.get("loops", 0) >= MAX_REVIEW_LOOPS:
            return "refuted"      # give up: keep the deterministic summary
        return "retry"

    g = StateGraph(QualityState)
    g.add_node("tailor", tailor)
    g.add_node("review", review)
    g.set_entry_point("tailor")
    g.add_edge("tailor", "review")
    g.add_conditional_edges("review", route,
                            {"done": END, "refuted": END, "retry": "tailor"})
    return g.compile()


def run_quality_pass(llm, jd_text: str, evidence: list[dict],
                     baseline_summary: str) -> dict:
    """Returns {summary_text} on a grounded improvement, {} to keep the
    deterministic summary, or {error} on infrastructure failure."""
    graph = make_graph(llm)
    out: QualityState = graph.invoke({
        "jd_text": jd_text, "evidence": evidence,
        "baseline_summary": baseline_summary, "loops": 0,
    })
    if out.get("error"):
        return {"error": out["error"]}
    if out.get("verdict", "").upper().startswith("GROUNDED") and out.get("proposal"):
        return {"summary_text": out["proposal"]}
    return {"refuted": out.get("verdict", "no grounded proposal")}
