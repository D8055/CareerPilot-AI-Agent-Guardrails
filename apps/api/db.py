"""Database layer. SQLite for local dev (zero-resident, lightweight rule);
set DATABASE_URL to a Neon Postgres URL at deploy — models are portable.
Vectors live in JSON columns at this scale; pgvector lands with the Phase 3
deploy migration."""
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, LargeBinary, String,
                        Text, create_engine, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    pw_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="owner")  # owner|viewer


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(255), default="")
    ats: Mapped[str] = mapped_column(String(64), default="")
    channel: Mapped[str] = mapped_column(String(32), default="unknown")
    jd_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="new")
    match: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_match: Mapped[int | None] = mapped_column(Integer, nullable=True)  # recruiter score
    llm_analysis: Mapped[str] = mapped_column(Text, default="")
    matched_keywords: Mapped[list] = mapped_column(JSON, default=list)
    missing_keywords: Mapped[list] = mapped_column(JSON, default=list)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CareerItem(Base):
    __tablename__ = "career_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(128), default="")   # pool bullet id
    kind: Mapped[str] = mapped_column(String(32))               # bullet|skill|summary|accomplishment
    section: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(Integer, default=1)
    evidence: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="pool")  # pool|owner
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)


class Artifact(Base):
    """Uploaded + generated files (master resume, tailored resume PDFs). Bytes
    live in the DB — local dev DB is gitignored, and deployed hosts have
    ephemeral filesystems (spec §7.2)."""
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="master_resume")  # master_resume|resume_pdf
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    data: Mapped[bytes] = mapped_column(LargeBinary)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {failures: [...]}
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    plan_json: Mapped[dict] = mapped_column(JSON)
    honesty_report: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(32), default="deterministic")
    quality_pass: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|n/a
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    mode: Mapped[str] = mapped_column(String(32), default="manual")
    result: Mapped[str] = mapped_column(String(32), default="applied")
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="keyword")  # keyword|form
    keyword: Mapped[str] = mapped_column(String(128), default="")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|answered
    source_job: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)


class Answer(Base):
    """The answer bank (ported policy): an unmatched form question is NEVER
    auto-answered — it pings the owner once; the reply is stored here so the
    same question is automatic forever after."""
    __tablename__ = "answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(Text)        # regex (falls back to substring)
    question: Mapped[str] = mapped_column(Text, default="")   # example question seen
    answer: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="learned")  # learned|manual
    uses: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class IntelligenceJob(Base):
    __tablename__ = "intelligence_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # tailor_quality|review|judge|answer_draft
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|leased|done|failed
    lease_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    runner_id: Mapped[str] = mapped_column(String(128), default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RunnerInfo(Base):
    __tablename__ = "runners"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_key: Mapped[str] = mapped_column(String(128))
    metrics: Mapped[dict] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Blocker(Base):
    """The 'waiting on Dhiren' state, first-class in the product."""
    __tablename__ = "blockers"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # B1..B10
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[str] = mapped_column(Text, default="")
    phase: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[str] = mapped_column(String(32), default="waiting_on_dhiren")
    # waiting_on_dhiren | resolved | deferred
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


def make_engine(db_url: str | None = None):
    url = db_url or os.environ.get("DATABASE_URL",
                                   f"sqlite:///{REPO_ROOT / 'data' / 'careerpilot.db'}")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


# additive column migrations for existing SQLite dev DBs (create_all only
# creates missing tables, never missing columns)
_MIGRATIONS = [
    ("career_items", "source", "ALTER TABLE career_items ADD COLUMN source VARCHAR(16) DEFAULT 'pool'"),
    ("jobs", "matched_keywords", "ALTER TABLE jobs ADD COLUMN matched_keywords JSON"),
    ("questions", "kind", "ALTER TABLE questions ADD COLUMN kind VARCHAR(16) DEFAULT 'keyword'"),
    ("artifacts", "plan_id", "ALTER TABLE artifacts ADD COLUMN plan_id INTEGER"),
    ("artifacts", "meta", "ALTER TABLE artifacts ADD COLUMN meta JSON"),
    ("jobs", "llm_match", "ALTER TABLE jobs ADD COLUMN llm_match INTEGER"),
    ("jobs", "llm_analysis", "ALTER TABLE jobs ADD COLUMN llm_analysis TEXT DEFAULT ''"),
]


def make_session_factory(engine) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        for table, column, ddl in _MIGRATIONS:
            cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))] \
                if engine.dialect.name == "sqlite" else []
            if engine.dialect.name == "sqlite" and column not in cols:
                conn.execute(text(ddl))
                conn.commit()
    return sessionmaker(bind=engine, expire_on_commit=False)
