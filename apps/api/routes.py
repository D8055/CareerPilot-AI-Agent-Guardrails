"""All REST routes. Reads need any authenticated user; writes need owner;
the runner uses its own token on /intelligence and /runners."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import services
from auth import (create_token, current_user, require_owner, require_runner,
                  verify_password)
from db import (Blocker, IntelligenceJob, Job, Plan, Question, RunnerInfo,
                StatusEvent, User, utcnow)
from ws import manager

router = APIRouter()


def get_db(request: Request) -> Session:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


# ---------- auth ----------

class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.execute(select(User).filter_by(email=body.email)).scalar_one_or_none()
    if not user or not verify_password(body.password, user.pw_hash):
        raise HTTPException(401, "bad credentials")
    return {"access_token": create_token(user.email, user.role), "role": user.role}


@router.post("/auth/share")
def share_link(user: dict = Depends(require_owner)):
    """Read-only viewer token (7 days) for mentors/reviewers."""
    return {"viewer_token": create_token("viewer@share", "viewer", hours=24 * 7)}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"email": user["sub"], "role": user["role"]}


# ---------- jobs ----------

class JobBody(BaseModel):
    url: str = ""
    company: str = ""
    role: str = ""
    channel: str = "unknown"
    jd_text: str = ""


class StatusBody(BaseModel):
    status: str
    note: str = ""


def _job_dict(j: Job) -> dict:
    return {"id": j.id, "url": j.url, "company": j.company, "role": j.role,
            "ats": j.ats, "channel": j.channel, "status": j.status,
            "match": j.match, "llm_match": j.llm_match,
            "matched_keywords": j.matched_keywords or [],
            "missing_keywords": j.missing_keywords or [],
            "added_at": j.added_at.isoformat() if j.added_at else None}


@router.get("/jobs")
def list_jobs(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [_job_dict(j) for j in db.execute(
        select(Job).order_by(Job.added_at.desc())).scalars()]


def _apply_enrichment(job: Job, db: Session) -> str:
    """Fetch the posting and fill EMPTY fields only (owner input wins).
    Returns a plain-English note describing what happened."""
    import enrich
    try:
        found = enrich.enrich_from_url(job.url)
    except enrich.EnrichError as e:
        db.add(StatusEvent(job_id=job.id, status=job.status,
                           note=f"auto-enrich failed: {e}"))
        return f"auto-enrich failed: {e}"
    job.company = job.company or found["company"]
    job.role = job.role or found["role"]
    job.ats = job.ats or found["ats"]
    if job.channel in ("", "unknown"):
        job.channel = found["channel"]
    if not job.jd_text and found["jd_text"]:
        job.jd_text = found["jd_text"]
    got_jd = bool(job.jd_text)
    # jobs stay in the New Jobs stage until the owner hits Apply — enrichment
    # fills fields, it does not advance the pipeline (Saved-stage convention)
    note = (f"auto-enriched via {found['source']}: "
            f"{job.company or '?'} / {job.role or '?'}"
            + ("" if got_jd else " (no JD text found — paste it manually)"))
    db.add(StatusEvent(job_id=job.id, status=job.status, note=note))
    return note


@router.post("/jobs", status_code=201)
async def add_job(body: JobBody, user: dict = Depends(require_owner),
                  db: Session = Depends(get_db)):
    job = Job(**body.model_dump())
    db.add(job)
    db.flush()
    db.add(StatusEvent(job_id=job.id, status="new", note="added"))
    note = ""
    if job.url and not (job.company and job.role and job.jd_text):
        note = _apply_enrichment(job, db)
    db.commit()
    await manager.broadcast({"type": "job_added", "job": _job_dict(job)})
    out = _job_dict(job)
    out["enrichment"] = note
    return out


@router.post("/jobs/{job_id}/enrich")
async def enrich_job(job_id: int, user: dict = Depends(require_owner),
                     db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if not job.url:
        raise HTTPException(400, "job has no URL to enrich from")
    note = _apply_enrichment(job, db)
    db.commit()
    await manager.broadcast({"type": "status_changed", "job_id": job_id,
                             "status": job.status})
    out = _job_dict(job)
    out["enrichment"] = note
    return out


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int, user: dict = Depends(require_owner),
                     db: Session = Depends(get_db)):
    """Remove a job and everything hanging off it (plans, PDFs, events,
    queued passes). Questions survive: asked-once-ever must hold even if the
    job that raised them is gone."""
    from db import Artifact
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    db.query(StatusEvent).filter_by(job_id=job_id).delete()
    db.query(Plan).filter_by(job_id=job_id).delete()
    db.query(Artifact).filter_by(job_id=job_id).delete()
    for ij in db.execute(select(IntelligenceJob)).scalars():
        if (ij.payload or {}).get("job_id") == job_id:
            db.delete(ij)
    db.delete(job)
    db.commit()
    await manager.broadcast({"type": "job_deleted", "job_id": job_id})
    return {"ok": True}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: dict = Depends(current_user),
            db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    events = db.execute(select(StatusEvent).filter_by(job_id=job_id)
                        .order_by(StatusEvent.ts)).scalars()
    plans = db.execute(select(Plan).filter_by(job_id=job_id)
                       .order_by(Plan.created_at.desc())).scalars()
    d = _job_dict(job)
    d["jd_text"] = job.jd_text
    d["llm_analysis"] = job.llm_analysis
    d["status_events"] = [{"status": e.status, "note": e.note,
                           "ts": e.ts.isoformat()} for e in events]
    d["plans"] = [{"id": p.id, "created_by": p.created_by,
                   "quality_pass": p.quality_pass,
                   "summary_text": p.plan_json.get("summary_text", ""),
                   "created_at": p.created_at.isoformat()} for p in plans]
    return d


@router.patch("/jobs/{job_id}/status")
async def set_status(job_id: int, body: StatusBody,
                     user: dict = Depends(require_owner),
                     db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job.status = body.status
    db.add(StatusEvent(job_id=job_id, status=body.status, note=body.note))
    db.commit()
    await manager.broadcast({"type": "status_changed", "job_id": job_id,
                             "status": body.status})
    return _job_dict(job)


class JDBody(BaseModel):
    jd_text: str = ""


@router.post("/jobs/{job_id}/tailor")
async def tailor_job(job_id: int, body: JDBody | None = None,
                     user: dict = Depends(require_owner),
                     db: Session = Depends(get_db)):
    """Apply: queue the job for AI tailoring (the runner's Claude pass picks
    the bullets, writes the summary, and scores the match)."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if body and body.jd_text:
        job.jd_text = body.jd_text
    if not job.jd_text:
        raise HTTPException(400, "job has no JD text")
    report = services.request_ai_tailor(db, job)
    await manager.broadcast({"type": "tailoring", "job_id": job_id})
    return report


@router.get("/tailor/menu")
def tailor_menu(user: dict = Depends(current_user)):
    """The verified selection menu the AI tailor chooses from (runner uses
    this; owner/viewer may inspect it)."""
    return services.pool_menu(services.get_pool())


class ValidateBody(BaseModel):
    plan: dict


@router.post("/tailor/validate")
def validate_plan(body: ValidateBody, user: dict = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Dry-run the honesty guard on a candidate plan (the runner's repair
    loop uses this before submitting)."""
    from careerpilot_shared import validate_pool_plan
    pool = services.get_pool()
    plan = services.normalize_ai_plan(pool, dict(body.plan))
    return {"violations": validate_pool_plan(pool, plan,
                                             services.owner_corpus(db))}


@router.get("/jobs/{job_id}/resume")
def tailored_resume(job_id: int, user: dict = Depends(current_user),
                    db: Session = Depends(get_db)):
    """The tailored resume CONTENT for this job (latest plan, resolved
    against the pool). Docx/PDF rendering arrives with the runner phase."""
    plan = db.execute(select(Plan).filter_by(job_id=job_id)
                      .order_by(Plan.created_at.desc())).scalars().first()
    if not plan:
        raise HTTPException(404, "no tailored plan yet — run Tailor first")
    resume = services.resolve_plan_to_resume(services.get_pool(), plan.plan_json)
    return {"job_id": job_id, "plan_id": plan.id, "created_by": plan.created_by,
            "quality_pass": plan.quality_pass, "resume": resume}


@router.get("/jobs/{job_id}/resume/status")
def resume_pdf_status(job_id: int, user: dict = Depends(current_user),
                      db: Session = Depends(get_db)):
    return services.resume_pdf_status(db, job_id)


@router.post("/jobs/{job_id}/resume/render")
async def render_resume(job_id: int, variant: str = "twopage",
                        user: dict = Depends(require_owner),
                        db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    try:
        result = services.render_resume_pdf(db, job, variant)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    await manager.broadcast({"type": "resume_rendered", "job_id": job_id,
                             "variant": variant, "verified": result["verified"]})
    return result


@router.get("/jobs/{job_id}/resume.pdf")
def resume_pdf(job_id: int, variant: str = "twopage",
               user: dict = Depends(current_user),
               db: Session = Depends(get_db)):
    """The tailored PDF for a variant, served inline so it renders in an
    <iframe> / new tab. Auth rides the fetch (the frontend turns the blob into
    an object URL — no token ever appears in a URL)."""
    from fastapi.responses import Response
    art = services._variant_artifact(db, job_id, variant)
    if not art:
        raise HTTPException(404, "no rendered PDF for this variant — render it first")
    return Response(content=art.data, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{art.filename}"'})


@router.get("/jobs/{job_id}/plan")
def latest_plan(job_id: int, user: dict = Depends(current_user),
                db: Session = Depends(get_db)):
    plan = db.execute(select(Plan).filter_by(job_id=job_id)
                      .order_by(Plan.created_at.desc())).scalars().first()
    if not plan:
        raise HTTPException(404, "no plan yet")
    return {"id": plan.id, "job_id": job_id, "plan": plan.plan_json,
            "created_by": plan.created_by, "quality_pass": plan.quality_pass,
            "honesty_report": plan.honesty_report}


# ---------- career record / RAG ----------

@router.get("/career")
def career(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from db import CareerItem
    items = db.execute(select(CareerItem)).scalars()
    return [{"id": i.id, "ref": i.ref, "kind": i.kind, "section": i.section,
             "text": i.text, "tier": i.tier, "source": i.source} for i in items]


class CareerItemBody(BaseModel):
    text: str
    kind: str = "bullet"
    section: str = ""


@router.post("/career/items", status_code=201)
def add_career_item(body: CareerItemBody, user: dict = Depends(require_owner),
                    db: Session = Depends(get_db)):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    item = services.add_career_item(db, body.text, body.kind, body.section)
    return {"id": item.id, "kind": item.kind, "section": item.section,
            "text": item.text, "tier": item.tier, "source": item.source}


class CareerItemEditBody(BaseModel):
    text: str


@router.patch("/career/items/{item_id}")
def edit_career_item(item_id: int, body: CareerItemEditBody,
                     user: dict = Depends(require_owner),
                     db: Session = Depends(get_db)):
    from db import CareerItem
    item = db.get(CareerItem, item_id)
    if not item:
        raise HTTPException(404, "no such item")
    try:
        item = services.edit_career_item(db, item, body.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": item.id, "ref": item.ref, "kind": item.kind,
            "section": item.section, "text": item.text, "tier": item.tier,
            "source": item.source}


@router.delete("/career/items/{item_id}")
def delete_career_item(item_id: int, user: dict = Depends(require_owner),
                       db: Session = Depends(get_db)):
    from db import CareerItem
    item = db.get(CareerItem, item_id)
    if not item:
        raise HTTPException(404, "no such item")
    if item.source != "owner":
        raise HTTPException(400, "pool items are managed by the pool file, "
                                 "not deletable here")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ---------- resume upload ----------

@router.get("/resume")
def resume_meta(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from db import Artifact
    a = db.execute(select(Artifact).filter_by(kind="master_resume")
                   .order_by(Artifact.ts.desc())).scalars().first()
    if not a:
        return {"uploaded": False}
    return {"uploaded": True, "id": a.id, "filename": a.filename,
            "content_type": a.content_type, "size": len(a.data),
            "ts": a.ts.isoformat()}


@router.post("/resume", status_code=201)
async def upload_resume(request: Request, user: dict = Depends(require_owner),
                        db: Session = Depends(get_db)):
    from starlette.datastructures import UploadFile

    from db import Artifact
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise HTTPException(400, "send multipart form data with a 'file' field")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > 10_000_000:
        raise HTTPException(400, "file too large (10 MB max)")
    a = Artifact(kind="master_resume", filename=file.filename or "resume",
                 content_type=file.content_type or "application/octet-stream",
                 data=data)
    db.add(a)
    db.commit()
    return {"id": a.id, "filename": a.filename, "size": len(data)}


@router.get("/resume/download")
def download_resume(user: dict = Depends(current_user),
                    db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from db import Artifact
    a = db.execute(select(Artifact).filter_by(kind="master_resume")
                   .order_by(Artifact.ts.desc())).scalars().first()
    if not a:
        raise HTTPException(404, "no resume uploaded yet")
    return Response(content=a.data, media_type=a.content_type, headers={
        "Content-Disposition": f'attachment; filename="{a.filename}"'})


class RagBody(BaseModel):
    text: str
    k: int = 5


@router.post("/rag/query")
def rag(body: RagBody, user: dict = Depends(current_user),
        db: Session = Depends(get_db)):
    return services.rag_query(db, body.text, body.k)


# ---------- questions ----------

@router.get("/questions")
def questions(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": q.id, "kind": q.kind, "keyword": q.keyword,
             "question": q.question, "answer": q.answer, "status": q.status,
             "source_job": q.source_job}
            for q in db.execute(select(Question)).scalars()]


class AnswerBody(BaseModel):
    answer: str


@router.post("/questions/{qid}/answer")
async def answer_question(qid: int, body: AnswerBody,
                          user: dict = Depends(require_owner),
                          db: Session = Depends(get_db)):
    """The applier's confirmation loop: 'no' just closes the question; real
    evidence becomes a confirmed career item and the source job re-tailors,
    so the match reflects it immediately."""
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "no such question")
    q.answer = body.answer
    q.status = "answered"
    answer = body.answer.strip()
    if q.kind == "form":
        # form questions feed the answer bank verbatim — automatic next time
        a = services.learn_answer(db, q.question, answer)
        return {"id": q.id, "status": q.status, "learned_answer_id": a.id}
    confirmed = answer and answer.lower() not in ("no", "no.", "n", "none", "nope")
    result: dict = {"id": q.id, "status": q.status, "confirmed": bool(confirmed)}
    if confirmed:
        item = services.add_career_item(
            db, f"{q.keyword}: {answer}", kind="confirmation",
            section=f"confirmed: {q.keyword}")
        result["career_item_id"] = item.id
        job = db.get(Job, q.source_job) if q.source_job else None
        if job and job.jd_text:
            report = services.request_ai_tailor(db, job)
            result["retailored_job"] = job.id
            result["claude_connected"] = report["claude_connected"]
            result["new_match"] = job.match   # internal signal; AI score follows
            await manager.broadcast({"type": "tailoring", "job_id": job.id})
    db.commit()
    return result


# ---------- answer bank ----------

@router.get("/answers")
def list_answers(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from db import Answer
    return [{"id": a.id, "pattern": a.pattern, "question": a.question,
             "answer": a.answer, "source": a.source, "uses": a.uses}
            for a in db.execute(select(Answer)).scalars()]


class AnswerEntryBody(BaseModel):
    question: str = ""
    pattern: str = ""
    answer: str


@router.post("/answers", status_code=201)
def add_answer(body: AnswerEntryBody, user: dict = Depends(require_owner),
               db: Session = Depends(get_db)):
    from db import Answer
    if not body.answer.strip() or not (body.question.strip() or body.pattern.strip()):
        raise HTTPException(400, "need an answer plus a question or pattern")
    import re
    a = Answer(pattern=body.pattern.strip() or re.escape(body.question.strip().lower()),
               question=body.question.strip(), answer=body.answer.strip(),
               source="manual")
    db.add(a)
    db.commit()
    return {"id": a.id, "pattern": a.pattern, "answer": a.answer}


@router.delete("/answers/{aid}")
def delete_answer(aid: int, user: dict = Depends(require_owner),
                  db: Session = Depends(get_db)):
    from db import Answer
    a = db.get(Answer, aid)
    if not a:
        raise HTTPException(404, "no such answer")
    db.delete(a)
    db.commit()
    return {"ok": True}


class ResolveBody(BaseModel):
    question: str


@router.post("/answers/resolve")
def resolve_answer(body: ResolveBody, user: dict = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Bank hit -> the stored answer. Miss -> pings the owner (policy: an
    unmatched question is NEVER auto-answered)."""
    if not body.question.strip():
        raise HTTPException(400, "question is empty")
    return services.resolve_answer(db, body.question)


# ---------- attention ----------

@router.get("/attention")
def attention(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return services.attention(db)


@router.post("/intelligence/{iid}/retry")
async def retry_intelligence(iid: int, user: dict = Depends(require_owner),
                             db: Session = Depends(get_db)):
    job = db.get(IntelligenceJob, iid)
    if not job:
        raise HTTPException(404, "no such intelligence job")
    if job.status != "failed":
        raise HTTPException(400, f"only failed jobs can retry (status: {job.status})")
    job.status = "queued"
    job.result = None
    job.runner_id = ""
    job.lease_ts = None
    db.commit()
    await manager.broadcast({"type": "quality_pass", "intelligence_id": iid,
                             "status": "queued"})
    return {"id": iid, "status": "queued"}


@router.post("/intelligence/{iid}/dismiss")
def dismiss_intelligence(iid: int, user: dict = Depends(require_owner),
                         db: Session = Depends(get_db)):
    job = db.get(IntelligenceJob, iid)
    if not job:
        raise HTTPException(404, "no such intelligence job")
    job.result = {**(job.result or {}), "dismissed": True}
    db.commit()
    return {"id": iid, "dismissed": True}


# ---------- export ----------

@router.get("/export/jobs.csv")
def export_jobs(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    import csv
    import io

    from fastapi.responses import Response
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "company", "role", "status", "match", "channel", "ats",
                "added_at", "url"])
    for j in db.execute(select(Job).order_by(Job.id)).scalars():
        w.writerow([j.id, j.company, j.role, j.status, j.match, j.channel,
                    j.ats, j.added_at.isoformat() if j.added_at else "", j.url])
    return Response(content=buf.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="careerpilot_jobs.csv"'})


# ---------- evals ----------

@router.get("/evals")
def evals(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from db import EvalRun
    return [{"id": r.id, "matrix_key": r.matrix_key, "metrics": r.metrics,
             "ts": r.ts.isoformat()}
            for r in db.execute(select(EvalRun).order_by(EvalRun.ts.desc())).scalars()]


@router.post("/evals/run")
def run_evals(user: dict = Depends(require_owner), db: Session = Depends(get_db)):
    return services.run_evals(db)


# ---------- status: blockers, runners, stats ----------

@router.get("/status/blockers")
def blockers(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [{"code": b.code, "title": b.title, "detail": b.detail,
             "phase": b.phase, "status": b.status}
            for b in db.execute(select(Blocker).order_by(Blocker.code)).scalars()]


class BlockerBody(BaseModel):
    status: str  # waiting_on_dhiren | resolved | deferred


@router.patch("/status/blockers/{code}")
def set_blocker(code: str, body: BlockerBody,
                user: dict = Depends(require_owner),
                db: Session = Depends(get_db)):
    b = db.get(Blocker, code)
    if not b:
        raise HTTPException(404, "no such blocker")
    b.status = body.status
    db.commit()
    return {"code": b.code, "status": b.status}


@router.get("/status/runners")
def runners(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    from db import age_seconds
    rows = db.execute(select(RunnerInfo)).scalars().all()
    return [{"id": r.id, "hostname": r.hostname,
             "last_heartbeat": r.last_heartbeat.isoformat(),
             "online": age_seconds(r.last_heartbeat) < 120}
            for r in rows]


@router.get("/stats")
def stats(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return services.application_stats(db)


# ---------- runner endpoints (token-authed) ----------

@router.post("/runners/heartbeat")
def heartbeat(request: Request, tok: str = Depends(require_runner),
              db: Session = Depends(get_db)):
    rid = request.headers.get("x-runner-id", "runner-1")
    host = request.headers.get("x-runner-host", "")
    r = db.get(RunnerInfo, rid) or RunnerInfo(id=rid)
    r.hostname = host
    r.last_heartbeat = utcnow()
    db.merge(r)
    db.commit()
    return {"ok": True}


@router.post("/intelligence/lease")
def lease(request: Request, tok: str = Depends(require_runner),
          db: Session = Depends(get_db)):
    rid = request.headers.get("x-runner-id", "runner-1")
    job = db.execute(select(IntelligenceJob).filter_by(status="queued")
                     .order_by(IntelligenceJob.created_at)).scalars().first()
    if not job:
        return {"job": None}
    job.status = "leased"
    job.lease_ts = utcnow()
    job.runner_id = rid
    db.commit()
    return {"job": {"id": job.id, "kind": job.kind, "payload": job.payload}}


class CompleteBody(BaseModel):
    status: str = "done"   # done|failed
    result: dict = {}


@router.post("/intelligence/{iid}/complete")
async def complete(iid: int, body: CompleteBody,
                   tok: str = Depends(require_runner),
                   db: Session = Depends(get_db)):
    job = db.get(IntelligenceJob, iid)
    if not job:
        raise HTTPException(404, "no such intelligence job")
    job.status = body.status
    job.result = body.result
    # tailor_full: the AI's COMPLETE plan (selection + summary + score). The
    # honesty guard disposes of whatever the LLM proposed, no exceptions.
    if job.kind == "tailor_full":
        target = db.get(Job, (job.payload or {}).get("job_id", -1))
        if body.status == "done":
            ai_plan = body.result.get("plan")
            if target and isinstance(ai_plan, dict):
                violations = services.accept_ai_plan(
                    db, target, ai_plan, body.result.get("llm_match"),
                    body.result.get("analysis", ""))
                if violations:
                    job.status = "failed"
                    job.result = {"rejected_by_honesty_guard": violations}
            elif target:
                job.status = "failed"
                job.result = {"error": "AI returned no plan"}
        # any failure: never leave the job stuck in 'tailoring' limbo — it
        # returns to New Jobs (or stays tailored if an older plan exists)
        # and the failure shows in Attention with a Retry button
        if job.status == "failed" and target and target.status == "tailoring":
            has_plan = db.execute(select(Plan).filter_by(job_id=target.id)
                                  ).scalars().first() is not None
            target.status = "tailored" if has_plan else "new"
            db.add(StatusEvent(job_id=target.id, status=target.status,
                               note="AI tailoring failed — see Attention to retry"))
        db.commit()
        await manager.broadcast({"type": "tailored",
                                 "job_id": (job.payload or {}).get("job_id"),
                                 "status": job.status})
        return {"ok": True, "accepted": job.status == "done"}
    # a clean tailor_quality pass upgrades the plan it reviewed — but the
    # honesty guard disposes of whatever the LLM proposed, no exceptions
    if body.status == "done" and job.kind == "tailor_quality":
        # the recruiter's match score + analysis become the displayed match
        target = db.get(Job, (job.payload or {}).get("job_id", -1))
        if target:
            if isinstance(body.result.get("llm_match"), int):
                target.llm_match = max(0, min(100, body.result["llm_match"]))
            if body.result.get("analysis"):
                target.llm_analysis = body.result["analysis"]
        plan = db.get(Plan, (job.payload or {}).get("plan_id", -1))
        if plan:
            new_summary = body.result.get("summary_text", "")
            if new_summary:
                from careerpilot_shared import check_honesty, validate_pool_plan
                extra = services.owner_corpus(db)
                candidate = {**plan.plan_json, "summary_text": new_summary}
                violations = (check_honesty(new_summary, services.get_pool(), extra) +
                              validate_pool_plan(services.get_pool(), candidate, extra))
                if violations:
                    job.status = "failed"
                    job.result = {"rejected_by_honesty_guard": violations}
                else:
                    plan.plan_json = candidate
                    plan.created_by = "agent"
                    plan.quality_pass = "done"
            else:
                plan.quality_pass = "done"
    db.commit()
    await manager.broadcast({"type": "quality_pass", "intelligence_id": iid,
                             "status": body.status})
    return {"ok": True}
