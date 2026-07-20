"""CareerPilot MCP server — drives the product from any MCP client.

Connect from Claude Code:
    claude mcp add careerpilot -- python apps/api/mcp_server.py
(run from the repo root; uses the same local database as the API).

Seven tools per spec §2.4, all calling the same service layer as the REST API,
so the honesty boundary is identical.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from sqlalchemy import select  # noqa: E402

import services  # noqa: E402
from db import Job, Question, StatusEvent, make_engine, make_session_factory  # noqa: E402

mcp = FastMCP("careerpilot")
_factory = make_session_factory(make_engine())


@mcp.tool()
def search_jobs(query: str = "") -> list[dict]:
    """List jobs, optionally filtered by company/role/status substring."""
    q = query.lower()
    with _factory() as db:
        jobs = db.execute(select(Job)).scalars().all()
        return [{"id": j.id, "company": j.company, "role": j.role,
                 "status": j.status, "match": j.match, "url": j.url}
                for j in jobs
                if not q or q in f"{j.company} {j.role} {j.status}".lower()]


@mcp.tool()
def get_job(job_id: int) -> dict:
    """Full detail for one job: JD, match, missing keywords, latest plan."""
    with _factory() as db:
        j = db.get(Job, job_id)
        if not j:
            return {"error": f"no job {job_id}"}
        return {"id": j.id, "company": j.company, "role": j.role,
                "status": j.status, "match": j.match,
                "missing_keywords": j.missing_keywords or [],
                "jd_text": j.jd_text[:2000], "url": j.url}


@mcp.tool()
def add_job_by_url(url: str, company: str = "", role: str = "",
                   jd_text: str = "") -> dict:
    """Add a job to the pipeline (curated — the queue is never scraped)."""
    with _factory() as db:
        job = Job(url=url, company=company, role=role, jd_text=jd_text)
        db.add(job)
        db.flush()
        db.add(StatusEvent(job_id=job.id, status="discovered", note="added via MCP"))
        db.commit()
        return {"id": job.id, "company": company, "status": "discovered"}


@mcp.tool()
def tailor_job(job_id: int) -> dict:
    """Deterministic tailor for a job: match score, keywords, selection plan.
    A quality-pass intelligence job is queued for the local runner."""
    with _factory() as db:
        job = db.get(Job, job_id)
        if not job:
            return {"error": f"no job {job_id}"}
        if not job.jd_text:
            return {"error": "job has no JD text — add it first"}
        report = services.tailor_and_store(db, job)
        return {k: report[k] for k in
                ("job_id", "plan_id", "match_score", "missing_keywords",
                 "quality_pass")}


@mcp.tool()
def get_career_record() -> list[dict]:
    """The verified career pool as indexed items (Tier-1 only)."""
    with _factory() as db:
        from db import CareerItem
        return [{"ref": i.ref, "kind": i.kind, "section": i.section,
                 "text": i.text}
                for i in db.execute(select(CareerItem)).scalars()]


@mcp.tool()
def answer_question(question_id: int, answer: str) -> dict:
    """Answer an open match-boost question (truthful answers only)."""
    with _factory() as db:
        q = db.get(Question, question_id)
        if not q:
            return {"error": f"no question {question_id}"}
        q.answer = answer
        q.status = "answered"
        db.commit()
        return {"id": q.id, "status": "answered"}


@mcp.tool()
def application_stats() -> dict:
    """Pipeline funnel counts, pending quality passes, waiting-on-owner items."""
    with _factory() as db:
        return services.application_stats(db)


if __name__ == "__main__":
    mcp.run()   # stdio transport — what `claude mcp add` expects
