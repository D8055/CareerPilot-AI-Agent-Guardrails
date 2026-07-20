"""CareerPilot core API.

Deterministic and keyless by design: every endpoint works with no LLM, no API
key, and no network. Intelligence quality passes run on the local runner
(Claude Agent SDK on the owner's subscription) — see docs/careerpilot-spec.md.
"""
import os
import secrets
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))

import services  # noqa: E402
from auth import hash_password, verify_password  # noqa: E402
from careerpilot_shared import (build_pool_plan, extract_jd_terms,  # noqa: E402
                                match_score, validate_pool_plan)
from careerpilot_shared.models import TailorReport, TailorRequest  # noqa: E402
from db import User, make_engine, make_session_factory  # noqa: E402
from routes import router  # noqa: E402
from ws import manager  # noqa: E402


def create_app(db_url: str | None = None) -> FastAPI:
    app = FastAPI(
        title="CareerPilot API",
        description="Job search copilot with a hard honesty boundary: "
                    "tailoring SELECTS from a verified career pool, never invents.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CAREERPILOT_CORS",
                                     "http://localhost:3000").split(","),
        allow_methods=["*"], allow_headers=["*"], allow_credentials=True,
    )
    engine = make_engine(db_url)
    app.state.session_factory = make_session_factory(engine)

    with app.state.session_factory() as db:
        services.seed_blockers(db)
        if not db.query(services.CareerItem).count():
            services.etl_pool(db)
        email = os.environ.get("CAREERPILOT_OWNER_EMAIL", "dhirenrao@gmail.com")
        env_pw = os.environ.get("CAREERPILOT_OWNER_PASSWORD")
        owner = db.execute(select(User).filter_by(email=email)).scalar_one_or_none()
        if owner is None:
            pw = env_pw
            if not pw:
                pw = secrets.token_urlsafe(12)
                print(f"[careerpilot] created owner {email} with one-time "
                      f"password: {pw}  (set CAREERPILOT_OWNER_PASSWORD to "
                      "control this)")
            db.add(User(email=email, pw_hash=hash_password(pw), role="owner"))
            db.commit()
        elif env_pw and not verify_password(env_pw, owner.pw_hash):
            # the env var always wins — otherwise a forgotten first-start
            # password locks the owner out of their own local app
            owner.pw_hash = hash_password(env_pw)
            db.commit()
            print("[careerpilot] owner password reset from "
                  "CAREERPILOT_OWNER_PASSWORD")

    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        pool = services.get_pool()
        return {"status": "ok", "pool_bullets": sum(
            len(e["bullets"]) for s in ("experience", "projects") for e in pool[s])}

    @app.post("/tailor", response_model=TailorReport)
    def tailor(req: TailorRequest) -> TailorReport:
        """Stateless deterministic tailor (no job row) — kept for quick tries
        and the Phase 0 contract."""
        pool = services.get_pool()
        matched, missing = extract_jd_terms(req.jd_text, pool)
        summary = (pool.get("meta") or {}).get("fallback_summary")
        if not summary:
            raise HTTPException(500, "pool has no fallback_summary")
        plan = build_pool_plan(pool, matched, summary_text=summary)
        violations = validate_pool_plan(pool, plan)
        if violations:
            raise HTTPException(500, f"deterministic plan failed validation: {violations}")
        return TailorReport(match_score=match_score(matched, missing),
                            matched_keywords=matched, missing_keywords=missing,
                            plan=plan)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await manager.connect(ws)
        try:
            while True:
                await ws.receive_text()   # keepalive pings from clients
        except WebSocketDisconnect:
            manager.disconnect(ws)

    return app


app = create_app()
