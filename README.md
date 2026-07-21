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

## Quickstart — one command

Double-click **`start.cmd`** (or run `.\start.ps1`). It installs anything
missing on first run, starts the API and the web app in minimized windows,
waits until both are healthy, and opens http://localhost:3000. Stop
everything with **`stop.cmd`**.

First API start prints a one-time owner password (or set
`CAREERPILOT_OWNER_PASSWORD` — the env var always wins, even later).

<details><summary>Manual start (what the script does)</summary>

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/ -q           # full test suite
.venv\Scripts\uvicorn main:app --app-dir apps/api  # http://127.0.0.1:8000/docs
cd apps/web; npm install; npm run dev              # http://localhost:3000
```
</details>

**Connect Claude (MCP):** `claude mcp add careerpilot -- python apps/api/mcp_server.py`
from the repo root — seven tools (search/add/tailor jobs, career record,
questions, stats) drive the product from any MCP client.

**Quality passes:** deterministic tailoring is instant and always live; the
local runner (`apps/runner/`) upgrades summaries via the Claude Agent SDK on
the owner's subscription. It is started manually — see its README.

**Blockers as state:** `GET /status/blockers` (and the Settings page) tracks
what is waiting on the owner (accounts, nods) vs resolved — the build's
outstanding needs live in the product, not in a doc.

## Privacy

The committed pool (`data/demo_career_pool.yaml`) is **fictional demo data**.
A real deployment points `CAREERPILOT_POOL` at a private pool file; `data/private/`
is gitignored for exactly that.
