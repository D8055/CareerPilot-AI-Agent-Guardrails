"""Domain services: pool ETL, tailoring persistence, evals, blockers, stats."""
import os
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot_shared import (build_pool_plan, check_honesty, extract_jd_terms,
                                load_pool, match_score, validate_pool_plan)

from db import (Blocker, CareerItem, EvalRun, IntelligenceJob, Job, Outbox, Plan,
                Question, StatusEvent)
from rag import cosine, get_embedder

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POOL = REPO_ROOT / "data" / "demo_career_pool.yaml"
EVAL_SET = REPO_ROOT / "data" / "eval_retrieval.yaml"


def get_pool() -> dict:
    return load_pool(os.environ.get("CAREERPILOT_POOL", DEFAULT_POOL))


# ---------- ETL: career pool -> career_items (the RAG index) ----------

def etl_pool(db: Session) -> int:
    """Idempotent: wipes and re-indexes career_items from the active pool."""
    pool = get_pool()
    db.query(CareerItem).delete()
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


def rag_query(db: Session, text: str, k: int = 5) -> list[dict]:
    qv = get_embedder().embed([text])[0]
    rows = db.execute(select(CareerItem)).scalars().all()
    scored = sorted(((cosine(qv, r.embedding or []), r) for r in rows),
                    key=lambda t: -t[0])[:k]
    return [{"id": r.id, "ref": r.ref, "kind": r.kind, "section": r.section,
             "text": r.text, "score": round(s, 4)} for s, r in scored]


# ---------- tailoring ----------

def tailor_and_store(db: Session, job: Job) -> dict:
    """Deterministic fast path: instant plan + honesty validation, then a
    quality-pass intelligence job is queued for the runner."""
    pool = get_pool()
    matched, missing = extract_jd_terms(job.jd_text, pool) if job.jd_text else ([], [])
    score = match_score(matched, missing)
    summary = (pool.get("meta") or {}).get("fallback_summary", "")
    plan = build_pool_plan(pool, matched, summary_text=summary)
    violations = validate_pool_plan(pool, plan)
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
    db.commit()
    return {"job_id": job.id, "plan_id": row.id, "match_score": score,
            "matched_keywords": matched, "missing_keywords": missing,
            "plan": plan, "plan_source": "deterministic",
            "quality_pass": "pending"}


# ---------- evals (100% deterministic — the CI gates) ----------

def run_evals(db: Session) -> dict:
    pool = get_pool()
    metrics: dict = {"embedder": get_embedder().name}

    hits = total = 0
    if EVAL_SET.exists():
        with open(EVAL_SET, encoding="utf-8") as f:
            pairs = yaml.safe_load(f)["pairs"]
        for p in pairs:
            total += 1
            top = rag_query(db, p["jd"], k=5)
            if set(p["expected"]) & {t["ref"] for t in top}:
                hits += 1
    metrics["retrieval_pairs"] = total
    metrics["retrieval_recall_at_5"] = round(hits / total, 3) if total else None

    # honesty: the fallback summary and every stored plan summary must be clean
    violations = len(check_honesty(pool["meta"]["fallback_summary"], pool))
    for plan in db.execute(select(Plan)).scalars():
        violations += len(check_honesty(plan.plan_json.get("summary_text", ""), pool))
    metrics["honesty_violations"] = violations

    run = EvalRun(matrix_key=f"deterministic|{get_embedder().name}", metrics=metrics)
    db.add(run)
    db.commit()
    return {"id": run.id, "matrix_key": run.matrix_key, "metrics": metrics}


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
