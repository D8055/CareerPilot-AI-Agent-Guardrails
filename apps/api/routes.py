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
            "match": j.match, "matched_keywords": j.matched_keywords or [],
            "missing_keywords": j.missing_keywords or [],
            "added_at": j.added_at.isoformat() if j.added_at else None}


@router.get("/jobs")
def list_jobs(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return [_job_dict(j) for j in db.execute(
        select(Job).order_by(Job.added_at.desc())).scalars()]


@router.post("/jobs", status_code=201)
async def add_job(body: JobBody, user: dict = Depends(require_owner),
                  db: Session = Depends(get_db)):
    job = Job(**body.model_dump())
    db.add(job)
    db.flush()
    db.add(StatusEvent(job_id=job.id, status="discovered", note="added"))
    db.commit()
    await manager.broadcast({"type": "job_added", "job": _job_dict(job)})
    return _job_dict(job)


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
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if body and body.jd_text:
        job.jd_text = body.jd_text
    if not job.jd_text:
        raise HTTPException(400, "job has no JD text")
    report = services.tailor_and_store(db, job)
    await manager.broadcast({"type": "tailored", "job_id": job_id,
                             "match": report["match_score"]})
    return report


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
             "text": i.text, "tier": i.tier} for i in items]


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
    return [{"id": q.id, "keyword": q.keyword, "question": q.question,
             "answer": q.answer, "status": q.status, "source_job": q.source_job}
            for q in db.execute(select(Question)).scalars()]


class AnswerBody(BaseModel):
    answer: str


@router.post("/questions/{qid}/answer")
def answer_question(qid: int, body: AnswerBody,
                    user: dict = Depends(require_owner),
                    db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "no such question")
    q.answer = body.answer
    q.status = "answered"
    db.commit()
    return {"id": q.id, "status": q.status}


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
    rows = db.execute(select(RunnerInfo)).scalars().all()
    return [{"id": r.id, "hostname": r.hostname,
             "last_heartbeat": r.last_heartbeat.isoformat(),
             "online": (utcnow() - r.last_heartbeat).total_seconds() < 120}
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
    # a clean tailor_quality pass upgrades the plan it reviewed — but the
    # honesty guard disposes of whatever the LLM proposed, no exceptions
    if body.status == "done" and job.kind == "tailor_quality":
        plan = db.get(Plan, (job.payload or {}).get("plan_id", -1))
        if plan:
            new_summary = body.result.get("summary_text", "")
            if new_summary:
                from careerpilot_shared import check_honesty, validate_pool_plan
                candidate = {**plan.plan_json, "summary_text": new_summary}
                violations = (check_honesty(new_summary, services.get_pool()) +
                              validate_pool_plan(services.get_pool(), candidate))
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
