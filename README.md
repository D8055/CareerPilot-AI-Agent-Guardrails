# CareerPilot

CareerPilot is a personal job search assistant. It reads job postings, matches
them against my real work history, and drafts a tailored resume for each one.
Strict rules keep it honest: it never invents experience and a human approves
every application. Built with Python, Next.js, Postgres, and AI agents powered
by Claude.

**Hard rules**
- **Zero API spend.** No paid LLM API calls anywhere — no API key code paths
  exist. Intelligence runs through the owner's Claude subscription (Agent SDK +
  MCP) on a local runner; CI and the deployed API are fully deterministic.
- **Truthful content only.** Tailoring SELECTS from a verified career pool.
  Keywords a posting wants but the pool cannot back are flagged, never added.
- Human confirm before any submission; rate caps on any automated applying; no
  CAPTCHA circumvention; credentials never in code.

Full architecture and phase plan: [docs/careerpilot-spec.md](docs/careerpilot-spec.md).

## Layout

```
apps/web/         Next.js + TypeScript + Tailwind (Phase 2)
apps/api/         FastAPI core — deterministic tailor, REST, MCP mount
apps/runner/      Local agent runner — LangGraph + Claude Agent SDK (Phase 1)
apps/analytics/   Spring Boot + Redpanda + MySQL demo (Phase 4)
automations/n8n/  n8n flow exports (Phase 4)
packages/shared/  Career pool, JD analysis, honesty guard, plan validation
infra/            docker-compose (Postgres+pgvector, Redis), CI
data/             demo_career_pool.yaml — FICTIONAL seed data
```

## Quickstart (Phase 0)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/ -q          # ported test suite
.venv\Scripts\uvicorn main:app --app-dir apps/api  # http://127.0.0.1:8000/docs
```

Try it: `POST /tailor` with `{"jd_text": "React and .NET developer with SQL"}`
returns a match score, matched/missing keywords, and a validated selection plan.

## Privacy

The committed pool (`data/demo_career_pool.yaml`) is **fictional demo data**.
A real deployment points `CAREERPILOT_POOL` at a private pool file; `data/private/`
is gitignored for exactly that.
