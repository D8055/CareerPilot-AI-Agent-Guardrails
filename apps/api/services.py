"""Domain services: pool ETL, tailoring persistence, evals, blockers, stats."""
import os
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot_shared import (build_pool_plan, check_honesty, extract_jd_terms,
                                load_pool, match_score, validate_pool_plan)

from db import (Answer, Blocker, CareerItem, EvalRun, IntelligenceJob, Job,
                Outbox, Plan, Question, RunnerInfo, StatusEvent)
from rag import cosine, get_embedder

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_POOL = REPO_ROOT / "data" / "demo_career_pool.yaml"
PRIVATE_POOL = REPO_ROOT / "data" / "private" / "career_pool.yaml"
DEMO_EVAL_SET = REPO_ROOT / "data" / "eval_retrieval.yaml"
PRIVATE_EVAL_SET = REPO_ROOT / "data" / "private" / "eval_retrieval.yaml"


def pool_path() -> Path:
    """Resolution order: explicit env -> private real pool (gitignored,
    never committed) -> the fictional demo seed. Dropping a real pool file
    into data/private/ is all it takes to go live with real data."""
    env = os.environ.get("CAREERPILOT_POOL")
    if env:
        return Path(env)
    return PRIVATE_POOL if PRIVATE_POOL.exists() else DEMO_POOL


def eval_set_path() -> Path:
    env = os.environ.get("CAREERPILOT_EVAL_SET")
    if env:
        return Path(env)
    return PRIVATE_EVAL_SET if PRIVATE_EVAL_SET.exists() else DEMO_EVAL_SET


def get_pool() -> dict:
    return load_pool(pool_path())


# ---------- ETL: career pool -> career_items (the RAG index) ----------

def etl_pool(db: Session) -> int:
    """Idempotent: wipes and re-indexes the POOL-sourced career_items.
    Owner-added items (source='owner') are never touched."""
    pool = get_pool()
    db.query(CareerItem).filter_by(source="pool").delete()
    items: list[CareerItem] = []
    meta = pool.get("meta") or {}
    if meta.get("fallback_summary"):
        items.append(CareerItem(ref="fallback_summary", kind="summary",
                                section="summary", text=meta["fallback_summary"]))
    for g in pool["skills"]:
        items.append(CareerItem(ref=f"skills:{g['label']}", kind="skill",
                                section=g["label"],
                                text=g["label"] + ": " + ", ".join(g["items"])))
    for section in ("experience", "projects"):
        for entry in pool[section]:
            label = entry.get("org") or entry.get("name") or entry["id"]
            for b in entry["bullets"]:
                items.append(CareerItem(
                    ref=b["id"], kind="bullet", section=label,
                    text=b["text"] + " " + " ".join(b.get("keywords", [])),
                    evidence=entry.get("dates", "") or entry.get("stack", "")))
    for i, a in enumerate(pool["accomplishments"]):
        items.append(CareerItem(ref=f"accomplishment:{i}", kind="accomplishment",
                                section="accomplishments",
                                text=a["text"] + " " + " ".join(a.get("keywords", []))))
    emb = get_embedder()
    vectors = emb.embed([it.text for it in items])
    for it, v in zip(items, vectors):
        it.embedding = v
        db.add(it)
    db.commit()
    return len(items)


def add_career_item(db: Session, text: str, kind: str = "bullet",
                    section: str = "") -> CareerItem:
    """Owner-asserted plain-text addition to the career record. Embedded
    immediately so RAG evidence includes it from the next query on."""
    item = CareerItem(kind=kind or "bullet", section=section or "added by owner",
                      text=text.strip(), source="owner",
                      evidence="owner-added via UI",
                      embedding=get_embedder().embed([text.strip()])[0])
    db.add(item)
    db.commit()
    return item


def edit_career_item(db: Session, item: CareerItem, new_text: str) -> CareerItem:
    """Owner edits an item in place. Pool-sourced bullets write back to the
    pool YAML (single source of truth — plans render from the pool), then the
    item re-embeds. Owner-added items just update."""
    new_text = new_text.strip()
    if not new_text:
        raise ValueError("text is empty")
    if item.source == "pool":
        if item.kind != "bullet":
            raise ValueError("only bullets are editable in place; skills and the "
                             "summary are managed in the pool file")
        path = pool_path()
        with open(path, encoding="utf-8") as f:
            pool = yaml.safe_load(f)
        hit = False
        for section in ("experience", "projects"):
            for entry in pool[section]:
                for b in entry["bullets"]:
                    if b["id"] == item.ref:
                        b["text"] = new_text
                        # a stale metric that no longer appears would break
                        # metric bolding; drop it if it vanished from the text
                        if b.get("metric") and b["metric"] not in new_text:
                            b["metric"] = ""
                        hit = True
        if not hit:
            raise ValueError(f"bullet {item.ref!r} not found in the pool file")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(pool, f, allow_unicode=True, sort_keys=False, width=88)
    item.text = new_text
    item.embedding = get_embedder().embed([new_text])[0]
    db.commit()
    return item


def rag_query(db: Session, text: str, k: int = 5) -> list[dict]:
    qv = get_embedder().embed([text])[0]
    rows = db.execute(select(CareerItem)).scalars().all()
    scored = sorted(((cosine(qv, r.embedding or []), r) for r in rows),
                    key=lambda t: -t[0])[:k]
    return [{"id": r.id, "ref": r.ref, "kind": r.kind, "section": r.section,
             "text": r.text, "score": round(s, 4)} for s, r in scored]


# ---------- tailoring (the applier's method: deterministic plan + the
# match-boost question loop; confirmations widen the truthful corpus) ----------

def target_match() -> int:
    return int(os.environ.get("CAREERPILOT_TARGET_MATCH", "80"))


def owner_corpus(db: Session) -> str:
    """Owner-confirmed content counts as claimable, exactly like the
    applier's pool confirmations."""
    rows = db.execute(select(CareerItem).filter_by(source="owner")).scalars()
    return " ".join(r.text for r in rows)


def create_match_questions(db: Session, job: Job, missing: list[str],
                           score: int | None, limit: int = 5) -> int:
    """Ported from the applier: below-target matches raise Apply-tab
    questions for the top missing keywords — asked once per keyword EVER;
    answers are one line of evidence or 'no'."""
    if score is None or score >= target_match() or not missing:
        return 0
    asked_ever = {q.keyword for q in db.execute(select(Question)).scalars()}
    made = 0
    for kw in missing:
        if made >= limit:
            break
        if kw in asked_ever:
            continue
        db.add(Question(
            keyword=kw, source_job=job.id,
            question=(f"The {job.company} posting wants \"{kw}\" (current match "
                      f"{score}%, target {target_match()}%). Do you have real, "
                      "verifiable experience with it? Answer with one line of "
                      "evidence (what you built/did), or 'no'.")))
        made += 1
    return made


def pool_menu(pool: dict) -> dict:
    """The compact selection menu the AI tailor chooses from: every verified
    bullet by id, with the selection bounds the validator will enforce."""
    return {
        "summary_rules": "25-80 words, one paragraph, only facts present in "
                         "this menu, no hyphens, no em dashes",
        "experience": [{
            "id": r["id"], "org": r["org"], "title": r["title"],
            "select_min": r["select"]["min"], "select_max": r["select"]["max"],
            "bullets": [{"id": b["id"], "text": b["text"]} for b in r["bullets"]],
        } for r in pool["experience"]],
        "projects_pick_exactly": 3,
        "projects": [{
            "id": p["id"], "name": p["name"],
            "select_min": p.get("select", {}).get("min", 2),
            "select_max": p.get("select", {}).get("max", 2),
            "bullets": [{"id": b["id"], "text": b["text"]} for b in p["bullets"]],
        } for p in pool["projects"]],
        "skills": [{"label": g["label"], "items": g["items"]} for g in pool["skills"]],
    }


def claude_connected(db: Session) -> bool:
    """Is a runner heartbeating? That IS 'Claude is hooked up'."""
    from db import age_seconds
    return any(age_seconds(r.last_heartbeat) < 120
               for r in db.execute(select(RunnerInfo)).scalars())


def request_ai_tailor(db: Session, job: Job) -> dict:
    """Apply. Tailoring is AI-first: the full-tailor pass is ALWAYS queued for
    Claude. If Claude is hooked up (runner heartbeating) the job waits in
    'tailoring' for the AI result. If not, the script fallback tailors it
    immediately — clearly labeled as such — and Claude's pass upgrades it
    whenever the runner comes online. The keyword machinery runs internally
    to raise confirmation questions; its number is only ever shown as the
    labeled script fallback."""
    pool = get_pool()
    extra = owner_corpus(db)
    matched, missing = extract_jd_terms(job.jd_text, pool, extra)
    internal_score = match_score(matched, missing)
    job.match = internal_score
    job.matched_keywords = matched
    job.missing_keywords = missing
    connected = claude_connected(db)

    db.flush()
    db.add(IntelligenceJob(kind="tailor_full", payload={"job_id": job.id}))
    questions_created = create_match_questions(db, job, missing, internal_score)

    if connected:
        job.status = "tailoring"
        db.add(StatusEvent(job_id=job.id, status="tailoring",
                           note="sent to Claude for tailoring"))
    else:
        # script fallback: a valid resume NOW, upgraded by Claude later
        summary = (pool.get("meta") or {}).get("fallback_summary", "")
        plan = build_pool_plan(pool, matched, summary_text=summary)
        violations = validate_pool_plan(pool, plan, extra)
        if violations:
            raise ValueError(f"fallback plan failed validation: {violations}")
        db.add(Plan(job_id=job.id, plan_json=plan, honesty_report=[],
                    created_by="deterministic", quality_pass="pending"))
        job.status = "tailored"
        db.add(StatusEvent(job_id=job.id, status="tailored",
                           note="script fallback (Claude not hooked up); AI "
                                "pass queued for when it connects"))
    db.add(Outbox(topic="application-events",
                  payload={"event": "tailoring", "job_id": job.id}))
    db.commit()
    return {"job_id": job.id, "status": job.status,
            "claude_connected": connected, "queued": True,
            "questions_created": questions_created}


def normalize_ai_plan(pool: dict, plan: dict) -> dict:
    """Fix formatting-only deviations in the AI's plan: group and role ORDER
    are fixed by the pool, so realigning them is normalization, not
    authorship. Content (which items, which bullets, the summary) is never
    touched — the validator judges that."""
    by_label = {g.get("label"): g for g in plan.get("skills", [])
                if isinstance(g, dict)}
    if set(by_label) == {g["label"] for g in pool["skills"]}:
        plan["skills"] = [by_label[g["label"]] for g in pool["skills"]]
    by_id = {e.get("id"): e for e in plan.get("experience", [])
             if isinstance(e, dict)}
    if set(by_id) == {r["id"] for r in pool["experience"]}:
        plan["experience"] = [by_id[r["id"]] for r in pool["experience"]]
    plan.setdefault("summary_bold", "")
    return plan


def accept_ai_plan(db: Session, job: Job, plan: dict, llm_match_score,
                   analysis: str) -> list[str]:
    """Validate the AI's complete plan (selection-only, honesty-clean). Valid ->
    plan stored, job tailored, AI score live. Returns violations (empty = ok)."""
    pool = get_pool()
    extra = owner_corpus(db)
    plan = normalize_ai_plan(pool, plan)
    violations = validate_pool_plan(pool, plan, extra)
    if violations:
        return violations
    row = Plan(job_id=job.id, plan_json=plan, honesty_report=[],
               created_by="agent", quality_pass="done")
    db.add(row)
    if isinstance(llm_match_score, int):
        job.llm_match = max(0, min(100, llm_match_score))
    if analysis:
        job.llm_analysis = analysis
    # never regress a job the owner already moved forward (applied etc.)
    if job.status in ("tailoring", "tailored", "new", "discovered", "enriched"):
        job.status = "tailored"
    db.add(StatusEvent(job_id=job.id, status="tailored",
                       note="AI tailoring accepted by the honesty guard"))
    db.add(Outbox(topic="application-events",
                  payload={"event": "tailored", "job_id": job.id,
                           "match": job.llm_match}))
    db.commit()
    return []


def tailor_and_store(db: Session, job: Job) -> dict:
    """Deterministic engine — retained ONLY as the CI/test fixture and the
    stateless dev endpoint. Not on any user path (tailoring is purely AI)."""
    pool = get_pool()
    extra = owner_corpus(db)
    matched, missing = (extract_jd_terms(job.jd_text, pool, extra)
                        if job.jd_text else ([], []))
    score = match_score(matched, missing)
    summary = (pool.get("meta") or {}).get("fallback_summary", "")
    plan = build_pool_plan(pool, matched, summary_text=summary)
    violations = validate_pool_plan(pool, plan, extra)
    if violations:
        raise ValueError(f"deterministic plan failed validation: {violations}")

    row = Plan(job_id=job.id, plan_json=plan, honesty_report=violations,
               created_by="deterministic", quality_pass="pending")
    db.add(row)
    job.match = score
    job.matched_keywords = matched
    job.missing_keywords = missing
    job.status = "tailored"
    db.add(StatusEvent(job_id=job.id, status="tailored",
                       note=f"deterministic plan, match {score}"))
    db.flush()
    db.add(IntelligenceJob(kind="tailor_quality",
                           payload={"job_id": job.id, "plan_id": row.id}))
    db.add(Outbox(topic="application-events",
                  payload={"event": "tailored", "job_id": job.id, "match": score}))
    questions_created = create_match_questions(db, job, missing, score)
    db.commit()
    return {"job_id": job.id, "plan_id": row.id, "match_score": score,
            "matched_keywords": matched, "missing_keywords": missing,
            "plan": plan, "plan_source": "deterministic",
            "quality_pass": "pending",
            "questions_created": questions_created,
            "target_match": target_match()}


VARIANTS = ("onepage", "twopage")


def _variant_artifact(db: Session, job_id: int, variant: str):
    from db import Artifact
    for a in db.execute(select(Artifact).filter_by(kind="resume_pdf", job_id=job_id)
                        .order_by(Artifact.ts.desc())).scalars():
        if (a.meta or {}).get("variant", "twopage") == variant:
            return a
    return None


def render_resume_pdf(db: Session, job: Job, variant: str = "twopage") -> dict:
    """Generate the job's latest plan into a 1-page or 2-page resume PDF and
    cache it as an artifact. Pure Python (reportlab) — no Word, any host."""
    import resume_pdf as gen
    from db import Artifact

    if variant not in VARIANTS:
        raise RuntimeError(f"unknown variant {variant!r}")
    plan = db.execute(select(Plan).filter_by(job_id=job.id)
                      .order_by(Plan.created_at.desc())).scalars().first()
    if not plan:
        raise RuntimeError("tailor this job first — no plan to render.")

    pdf_bytes = gen.build_resume_pdf(get_pool(), plan.plan_json, variant)
    pages = gen.page_count(pdf_bytes)
    failures = []
    if variant == "onepage" and pages != 1:
        failures.append(f"1-page resume overflowed to {pages} pages")
    if variant == "twopage" and pages > 2:
        failures.append(f"2-page resume overflowed to {pages} pages")

    # replace any prior artifact for this job+variant
    old = _variant_artifact(db, job.id, variant)
    if old:
        db.delete(old)
    art = Artifact(kind="resume_pdf", job_id=job.id, plan_id=plan.id,
                   filename=f"{(job.company or 'resume').replace(' ', '_')}_{variant}.pdf",
                   content_type="application/pdf", data=pdf_bytes,
                   meta={"failures": failures, "variant": variant, "pages": pages})
    db.add(art)
    db.commit()
    return {"rendered": True, "variant": variant, "plan_id": plan.id,
            "verified": not failures, "failures": failures,
            "pages": pages, "size": len(pdf_bytes)}


def resume_pdf_status(db: Session, job_id: int) -> dict:
    latest_plan = db.execute(select(Plan).filter_by(job_id=job_id)
                             .order_by(Plan.created_at.desc())).scalars().first()
    variants = {}
    for variant in VARIANTS:
        a = _variant_artifact(db, job_id, variant)
        variants[variant] = {
            "rendered": a is not None,
            "verified": bool(a and not (a.meta or {}).get("failures")),
            "failures": (a.meta or {}).get("failures", []) if a else [],
            "pages": (a.meta or {}).get("pages") if a else None,
            "stale": bool(a and latest_plan and a.plan_id != latest_plan.id),
            "ts": a.ts.isoformat() if a else None,
        }
    return {
        "rendering_available": True,   # pure-Python generator, always available
        "has_plan": latest_plan is not None,
        "variants": variants,
    }


def _desc(text: str) -> str:
    """The resume rules: descriptions render hyphen-free (dates keep theirs)."""
    return " ".join(text.replace("-", " ").split())


def resolve_plan_to_resume(pool: dict, plan: dict) -> dict:
    """Expand a selection plan into the full tailored resume content —
    exactly what the docx renderer will produce, as structured data."""
    roles_by_id = {r["id"]: r for r in pool["experience"]}
    projects_by_id = {p["id"]: p for p in pool["projects"]}

    def bullets(entry: dict, source: dict) -> list[str]:
        by_id = {b["id"]: b for b in source["bullets"]}
        return [_desc(by_id[bid]["text"]) for bid in entry.get("bullets", [])
                if bid in by_id]

    return {
        "contact": pool["contact"],
        "summary": _desc(plan.get("summary_text", "")),
        "skills": [{"label": g["label"], "items": g["items"]}
                   for g in plan.get("skills", [])],
        "experience": [{
            "org": roles_by_id[e["id"]]["org"],
            "title": roles_by_id[e["id"]]["title"],
            "dates": roles_by_id[e["id"]].get("dates", ""),
            "bullets": bullets(e, roles_by_id[e["id"]]),
        } for e in plan.get("experience", []) if e.get("id") in roles_by_id],
        "projects": [{
            "name": projects_by_id[e["id"]]["name"],
            "stack": projects_by_id[e["id"]].get("stack", ""),
            "bullets": bullets(e, projects_by_id[e["id"]]),
        } for e in plan.get("projects", []) if e.get("id") in projects_by_id],
        "accomplishments": [_desc(a["text"]) for a in pool["accomplishments"]],
    }


# ---------- evals (100% deterministic — the CI gates) ----------

def run_evals(db: Session) -> dict:
    pool = get_pool()
    metrics: dict = {"embedder": get_embedder().name}

    hits = total = 0
    if eval_set_path().exists():
        with open(eval_set_path(), encoding="utf-8") as f:
            pairs = yaml.safe_load(f)["pairs"]
        for p in pairs:
            total += 1
            top = rag_query(db, p["jd"], k=5)
            if set(p["expected"]) & {t["ref"] for t in top}:
                hits += 1
    metrics["retrieval_pairs"] = total
    metrics["retrieval_recall_at_5"] = round(hits / total, 3) if total else None

    # honesty: the fallback summary and each job's LATEST plan (the one that
    # ships) must be clean; superseded history may predate a pool change
    extra = owner_corpus(db)
    violations = len(check_honesty(pool["meta"]["fallback_summary"], pool, extra))
    latest: dict[int, Plan] = {}
    for plan in db.execute(select(Plan).order_by(Plan.created_at)).scalars():
        latest[plan.job_id] = plan
    for plan in latest.values():
        violations += len(check_honesty(plan.plan_json.get("summary_text", ""),
                                        pool, extra))
    metrics["honesty_violations"] = violations
    metrics["plans_checked"] = len(latest)

    run = EvalRun(matrix_key=f"deterministic|{get_embedder().name}", metrics=metrics)
    db.add(run)
    db.commit()
    return {"id": run.id, "matrix_key": run.matrix_key, "metrics": metrics}


# ---------- answer bank (ported): learn-on-ping, never auto-answer ----------

def _norm_q(text: str) -> str:
    import re
    return re.sub(r"\s+", " ", text).strip().lower()


def resolve_answer(db: Session, question_text: str) -> dict:
    """Look a form question up in the bank. A hit bumps usage and returns
    the stored answer. A miss creates ONE open form-question ping for the
    owner (never auto-answered, never re-asked while one is open)."""
    import re
    norm = _norm_q(question_text)
    for a in db.execute(select(Answer)).scalars():
        try:
            hit = re.search(a.pattern, question_text, re.I) is not None
        except re.error:
            hit = a.pattern.lower() in norm
        if hit or _norm_q(a.question) == norm:
            a.uses += 1
            db.commit()
            return {"answer": a.answer, "answer_id": a.id, "matched": True}
    existing = [q for q in db.execute(
        select(Question).filter_by(kind="form", status="open")).scalars()
        if _norm_q(q.question) == norm]
    if existing:
        return {"answer": None, "matched": False, "question_id": existing[0].id,
                "note": "already waiting on the owner"}
    q = Question(kind="form", question=question_text)
    db.add(q)
    db.commit()
    return {"answer": None, "matched": False, "question_id": q.id,
            "note": "asked the owner; the reply will be reused automatically"}


def learn_answer(db: Session, question_text: str, answer_text: str) -> Answer:
    """Store a replied form question so it is automatic next time."""
    import re
    a = Answer(pattern=re.escape(_norm_q(question_text)),
               question=question_text, answer=answer_text, source="learned")
    db.add(a)
    db.commit()
    return a


# ---------- attention: everything that needs a human, in one place ----------

def attention(db: Session) -> dict:
    items = []
    for ij in db.execute(select(IntelligenceJob).filter_by(status="failed")).scalars():
        r = ij.result or {}
        if r.get("dismissed") or r.get("superseded"):
            continue
        job = db.get(Job, (ij.payload or {}).get("job_id", -1))
        detail = (r.get("error") or "; ".join(r.get("rejected_by_honesty_guard", []))
                  or "failed")
        items.append({"type": "quality_failed", "intelligence_id": ij.id,
                      "job_id": job.id if job else None,
                      "company": job.company if job else "",
                      "detail": detail})
    for job in db.execute(select(Job)).scalars():
        if job.jd_text or not job.url:
            continue
        events = db.execute(select(StatusEvent).filter_by(job_id=job.id)
                            .order_by(StatusEvent.ts.desc())).scalars().all()
        note = next((e.note for e in events if "auto-enrich failed" in e.note), None)
        if note:
            items.append({"type": "enrich_failed", "job_id": job.id,
                          "company": job.company or job.url, "detail": note})
    from db import age_seconds
    runners_online = sum(
        1 for r in db.execute(select(RunnerInfo)).scalars()
        if age_seconds(r.last_heartbeat) < 120)
    counts = {
        "open_questions": db.query(Question).filter_by(status="open").count(),
        "failed_items": len(items),
        "quality_pending": db.query(IntelligenceJob).filter_by(status="queued").count(),
        "runner_online": runners_online > 0,
    }
    return {"counts": counts, "items": items}


# ---------- blockers: the waiting-on-Dhiren state ----------

BLOCKER_SEED = [
    ("B1", "GitHub repo created + Phase 0 pushed", "", "0", "resolved"),
    ("B2", "Privacy call: real career data vs fictional demo pool in the repo",
     "Defaulted to demo-only; real pool loads privately via CAREERPILOT_POOL. "
     "Needs Dhiren's explicit nod (or overrule).", "0", "waiting_on_dhiren"),
    ("B3", "Vercel account + connect repo",
     "Hosts the web app. ~10 min, free. Claude cannot create accounts.",
     "2", "waiting_on_dhiren"),
    ("B4", "Neon account (Postgres + pgvector)",
     "Free tier includes pgvector. Set DATABASE_URL at deploy.", "2", "waiting_on_dhiren"),
    ("B5", "API container host (Render free tier or Fly.io)",
     "Free tiers cold-start ~30 s after idle; $5/mo Railway buys always-on.",
     "2", "waiting_on_dhiren"),
    ("B6", "Nod: runner may draw on the Claude Max plan",
     "The runner shares plan limits with interactive sessions; nightly batching "
     "keeps it polite. No dollars involved.", "1", "waiting_on_dhiren"),
    ("B7", "JDK 21 install (Temurin)",
     "Machine has Java 8; Spring Boot 3 needs 17+. Claude can run the winget "
     "install with permission when Phase 4 starts.", "4", "waiting_on_dhiren"),
    ("B8", "Slack workspace + bot token", "", "4", "waiting_on_dhiren"),
    ("B9", "Optional: free hosted-tier model for the one-off CrewAI benchmark",
     "Groq or Google AI Studio free quota, $0. Default: skip and do not claim "
     "CrewAI. Local models ruled out by the lightweight rule.", "3", "deferred"),
    ("B10", "Optional: Colab account for the LoRA fine-tune stretch", "", "5", "deferred"),
]


def seed_blockers(db: Session) -> None:
    if db.query(Blocker).count():
        return
    for code, title, detail, phase, status in BLOCKER_SEED:
        db.add(Blocker(code=code, title=title, detail=detail, phase=phase,
                       status=status))
    db.commit()


# ---------- stats ----------

def application_stats(db: Session) -> dict:
    by_status: dict[str, int] = {}
    for job in db.execute(select(Job)).scalars():
        by_status[job.status] = by_status.get(job.status, 0) + 1
    return {
        "jobs_total": sum(by_status.values()),
        "by_status": by_status,
        "plans": db.query(Plan).count(),
        "open_questions": db.query(Question).filter_by(status="open").count(),
        "quality_passes_pending":
            db.query(IntelligenceJob).filter_by(status="queued").count(),
        "waiting_on_dhiren":
            db.query(Blocker).filter_by(status="waiting_on_dhiren").count(),
    }
