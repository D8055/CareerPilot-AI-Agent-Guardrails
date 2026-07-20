# CareerPilot — architecture & build spec (rev 2 — subscription-powered, zero API spend)

**What:** a deployed, multi-agent job-search copilot — the productized successor of
this applier. **Why:** it is the exact system the target postings describe, it
honestly earns most of the open skill questions, and most domain logic already
exists here to port.

**Personal project, separate repo.** All honesty rules carry over: the product
never fabricates resume content, never solves CAPTCHAs, and rate-limits any
automated applying.

**Rev 2 changes (2026-07-20):**
- **ZERO API CREDITS — same hard rule as the applier.** All LLM work runs through
  Dhiren's existing Claude Max plan via the **Claude Agent SDK** (Claude Code's
  subscription auth) on a local runner, plus interactive Claude clients connected
  over **MCP**. No `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` code paths exist.
- Every previously identified breakage point now has its fix designed in (§7).
- Prerequisites & blockers are tracked in the spec itself (§8).
- **Lightweight footprint rule (Dhiren, 2026-07-20): nothing heavy runs on his
  PC.** No local LLMs (Ollama is out entirely), no GPU workloads. The heaviest
  local component is a ~100 MB CPU embedding model; Docker stacks (analytics,
  n8n) start on demand for demos and stop afterward — nothing stays resident.

---

## 1. System architecture

```mermaid
flowchart LR
  subgraph Client
    UI[Next.js + TypeScript + Tailwind\nVercel]
    CC[Claude Code / Desktop\n(Dhiren's Max plan)]
  end
  subgraph Core["Core API — FastAPI (free-tier host)"]
    API[REST + WebSocket]
    MCP[MCP mount\n(streamable HTTP)]
    DET[Deterministic fast path\n(ported tailor + honesty guard)]
    Q[intelligence_jobs queue]
  end
  subgraph Runner["Local agent runner — Dhiren's PC"]
    AG[LangGraph agent graph]
    SDK[Claude Agent SDK\n(subscription auth, NO api key)]
    REN[Resume renderer\n(Word COM — already proven)]
  end
  subgraph Data
    PG[(PostgreSQL + pgvector\nNeon free tier)]
    RD[(Redis — local compose;\nPostgres-backed queue in prod)]
  end
  subgraph Analytics["Analytics wing — LOCAL Docker demo only"]
    K[[Redpanda\n(Kafka API)]]
    SB[Spring Boot service\n(JDK 21)]
    MY[(MySQL)]
  end
  subgraph Automation
    N8N[n8n flow (compose)]
    SLK[Slack bot]
  end
  UI -- same-origin proxy --> API
  CC -- MCP one-liner --> MCP --> API
  API --> DET --> PG
  API --> Q
  AG -- polls queue / posts results --> API
  AG --> SDK
  AG --> REN
  API --> PG & RD
  API -- outbox --> K --> SB --> MY
  API -- webhook --> N8N --> SLK
```

**The core inversion vs rev 1:** the deployed API is fully deterministic and
keyless — it always works, instantly, using the ported tailor/validator/honesty
code. Intelligence (summary rewrites, adversarial review, LLM-judge evals) is a
*quality pass* executed by a local runner on Dhiren's machine, powered by his
Claude Max subscription through the Agent SDK. If the runner is offline, nothing
breaks — quality passes queue up and the UI shows a "pending quality pass" badge.

Monorepo layout:

```
careerpilot/
  apps/web/            # Next.js + TS + Tailwind (Vercel)
  apps/api/            # FastAPI — REST, WS, auth, MCP mount, deterministic tailor
  apps/runner/         # local agent runner: LangGraph graph + Claude Agent SDK + renderer
  apps/analytics/      # Spring Boot + Redpanda consumer + MySQL (local Docker demo)
  packages/shared/     # pydantic models, ported honesty guard/validators, prompts, rubrics
  automations/n8n/     # exported n8n flow JSON
  infra/               # docker-compose (pg+pgvector, redis, redpanda, n8n), CI
```

---

## 2. Component specs

### 2.1 Frontend — `apps/web` (Next.js, TypeScript, Tailwind CSS, Vercel)
- Pages: Dashboard (pipeline board: discovered → enriched → tailored → applied →
  outcome), Job detail (JD, match, missing keywords, resume preview, Q&A, quality-pass
  status), Career record (the pool, tiered, with confirmation flow), Evals
  (scoreboard), Settings (incl. the **"Connect Claude" panel**: a copy-paste
  `claude mcp add --transport http careerpilot <api-url>/mcp` one-liner and a
  Claude Desktop config snippet — linking the user's Claude plan is one command).
- Auth (designed for cross-origin reality — see §7.4): email+password → short-lived
  JWT access token held in memory + rotating refresh token; **all REST calls go
  through a Next.js rewrite proxy so cookies are first-party/same-origin**. The
  WebSocket connects directly to the API using a short-lived token in the
  subprotocol (cookies are never relied on cross-site). Roles: `owner`, `viewer`
  (read-only share link); RBAC middleware on every route; viewer role sees
  **redacted** contact info.
- Realtime: WebSocket channel for agent/runner progress events.
- Definition of done: deployed on Vercel, Lighthouse ≥ 90, dark mode, mobile-usable.

### 2.2 Core API — `apps/api` (FastAPI, PostgreSQL, free-tier host)
- REST: jobs CRUD, career-record CRUD (tier-gated), tailor trigger, application
  log, outcome tracking (status_events), eval runs, artifact serving. OpenAPI docs on.
- **Deterministic fast path:** the ported tailor plan/validate + honesty guard run
  server-side with no LLM. Every tailor request gets an immediate deterministic
  result; an `intelligence_jobs` row is enqueued for the runner's quality pass.
- **MCP mount (was a separate app in rev 1):** the MCP server is a streamable-HTTP
  mount on the same FastAPI app — one fewer deployment, identical resume claim.
  Tools: `search_jobs`, `get_job`, `add_job_by_url`, `tailor_job`,
  `get_career_record`, `answer_question`, `application_stats`. Bearer-token auth.
- Queueing: locally, Redis (RQ/arq) in compose — earns the skill with real code.
  In production, the queue and rate ledger are Postgres-backed (`intelligence_jobs`
  + a sliding-window table) so the deploy needs **no Redis add-on account**
  (Upstash free tier is an optional swap-in later).
- Emits `application-events` rows to the **outbox table**; a relay publishes to
  Redpanda when the analytics compose stack is up, and silently no-ops when it
  isn't — the core never depends on Kafka being alive.
- Definition of done: deployed (Neon Postgres + free-tier container host), CI
  running pytest + ruff on push, **CI is fully deterministic — no LLM calls ever**.

### 2.3 Local agent runner — `apps/runner` (LangGraph + Claude Agent SDK + renderer)
Runs on Dhiren's PC (manual start or a scheduled task). Polls `intelligence_jobs`
(leased with heartbeats), executes, posts results back over the API.

- **LLM access = Claude Agent SDK using Claude Code's existing subscription
  login. No API key exists anywhere in the repo; CI and the deployed API make
  zero LLM calls.** Usage draws on the Max plan's limits; the queue + backoff
  smooths bursts, and batch-heavy work (eval matrices) runs as nightly batches.
- LangGraph `StateGraph` with typed state (`JobState`: url, jd, profile_evidence,
  plan, render_report, verdicts):
  - **scout** — fetch/parse a posting from its link (public pages only).
  - **enricher** — extract company/role/JD; resolve canonical ATS URL.
  - **evidence_retriever** — RAG query against the career index (§2.5): top-k
    verified bullets + confirmations for this JD.
  - **tailor** — selection plan + summary; the ported validator + honesty guard
    run as a deterministic node — LLM proposes, code disposes.
  - **reviewer** — adversarial node: refute any claim not grounded in retrieved
    evidence; a refutation loops back to tailor (max 2 iterations).
  - **renderer** — Word COM rendering (the machine it runs on is the machine
    where Word COM is already proven); uploads docx/pdf/png artifacts to the API.
  - **applier (phase 5+, optional)** — form-filling via agent-browser CLI with
    human-confirm gate; rate-limited.
- Interrupts (LangGraph checkpoints) pause for human answers — the match-boost
  Q&A becomes a first-class graph interrupt surfaced in the UI.
- **Comparison crew (Phase 3):** the same tailor task in CrewAI. CrewAI expects a
  generic LLM endpoint; wrapping subscription auth into one is off-limits, and
  local models are ruled out by the lightweight rule. **Default: the live
  benchmark is deferred and CrewAI is NOT claimed** (honesty rule: no claim
  without a real run). Optional unlock (B9): a genuinely free hosted tier
  (e.g. Groq or Google AI Studio free quota) powers the one-off benchmark for
  both frameworks — same model for both, zero dollars, Dhiren's call.

### 2.4 Claude-plan integration (the two link points)
1. **Interactive:** any Claude client (Code, Desktop) connects to the product via
   the MCP mount — one `claude mcp add` command, shown ready-to-copy in Settings.
   Claude can then browse jobs, trigger tailors, answer questions, read stats.
2. **Autonomous:** the runner invokes the Claude Agent SDK headlessly for queued
   quality passes. Same subscription, no key, no marginal cost.
Both paths hit the same API with the same auth and the same honesty boundary.

### 2.5 RAG subsystem (pgvector + in-process embeddings)
- Index: career document sections, every pool bullet (+tier metadata), answered
  confirmations, past JDs, past tailoring rationales.
- **Embeddings: in-process CPU model via `fastembed`/sentence-transformers
  (bge-small-en) — pip-installable, free, runs everywhere including the deployed
  API and CI. This removes rev 1's Ollama dependency for embeddings entirely.**
  At ~100 MB and CPU-only it is the heaviest thing that ever runs locally, and
  it only runs at index/query time — within the lightweight rule.
- Chunking: per-bullet (already atomic) + per-JD-section.
- Query: JD → top-k evidence with scores; the tailor node consumes ONLY retrieved
  tier-1 evidence (retrieval is the honesty boundary, mirrored from this repo's
  validator).
- Definition of done: retrieval eval set (20 hand-labeled JD→bullet pairs —
  **source them from this repo's `data/store.db`, which already holds real JDs
  and accepted plans**), recall@5 reported on the Evals page.

### 2.6 Eval harness — `packages/shared` + `apps/api` + runner
- **CI gates are 100% deterministic:** honesty violations (ported guard as a hard
  metric), match-score delta vs deterministic baseline, retrieval recall. A prompt
  change that increases honesty violations fails the build — with no LLM in CI.
- **LLM-judge (summary quality, fixed rubric) runs on the runner** via the Agent
  SDK as queued batch jobs; results persist to `eval_runs` and render on the
  Evals page. Matrix runs: {model/config} × {prompt version} × {job sample}.

### 2.7 Analytics microservice — `apps/analytics` (Spring Boot, Redpanda, MySQL)
- **Local Docker Compose demo only — never deployed** (running Kafka in prod
  hosting is disproportionate cost). The outbox table is the production-side
  contract; the compose stack consumes it when up.
- **Redpanda instead of Kafka** in compose (single binary, Kafka-API-compatible,
  a fraction of the footprint) — the consumer code is standard Kafka client code,
  so the skill claim is intact.
- **Requires JDK 17+; machine currently has Java 8 → install Temurin 21 as a
  Phase 4 prerequisite** (winget, ~10 min).
- Consumes `application-events`; persists to MySQL; exposes `/stats/funnel`,
  `/stats/weekly`, `/stats/response-times`. Deliberately small (≈500 lines) but
  real: consumer groups, idempotent upserts, Flyway migrations, JUnit tests.

### 2.8 Automation — `automations/n8n` + Slack
- Self-hosted n8n (compose): webhook from the API on job-added → enrich status →
  Slack DM via bot ("New: Scale AI — AI Builder Intern — match 68%, 3 questions
  open"). Second flow: weekly digest. Zapier free-tier mirror optional.

### 2.9 Stretch — fine-tuning
LoRA on a small open model (Colab free tier — the one workload a Claude
subscription cannot cover) over the answered-questions corpus + tailoring
rationales; eval against the base model in the harness. Only claim after the
eval shows the delta.

---

## 3. Data model (Postgres)

- `users(id, email, pw_hash, role)`
- `jobs(id, url, company, role, ats, channel, jd_text, status, match,
  fit_score, missing_keywords json, added_at)` — fit/missing-keyword fields
  added in rev 2 (the Job detail page displays them; rev 1 omitted them)
- `status_events(id, job_id, status, note, ts)` — full outcome history (ported
  pattern from the applier; rev 1 had no history table)
- `career_items(id, kind[bullet|skill|confirmation], text, tier, evidence,
  redact_for_viewer bool, embedding vector)`
- `plans(id, job_id, json, honesty_report, created_by[deterministic|agent|human],
  quality_pass[pending|done|n/a])`
- `artifacts(id, job_id, kind[resume_docx|resume_pdf|preview_png], bytes bytea,
  sha, ts)` — bytea is fine at this scale (~200 resumes × ~200 KB); free-tier
  hosts have ephemeral filesystems, so artifacts live in the DB, not on disk
- `applications(id, job_id, mode, result, resume_artifact_id, ts)`
- `questions(id, keyword, question, answer, status, source_job)`
- `intelligence_jobs(id, kind[tailor_quality|review|judge|answer_draft],
  payload json, status[queued|leased|done|failed], lease_ts, runner_id, result json)`
- `runners(id, hostname, last_heartbeat)` — powers the "quality passes paused —
  runner offline" badge
- `eval_runs(id, matrix_key, metrics json, ts)`
- `outbox(id, topic, payload json, published_at nullable)`
- `rate_ledger(id, scope, window_start, count)` — Postgres-backed sliding window

---

## 4. Skills matrix — what he brings vs what each component earns

| Component | Existing skills applied (already Tier-1) | New skills EARNED (open questions) |
|---|---|---|
| Frontend | React, TypeScript, CSS, UI-state, pixel-accuracy discipline | **Next.js, Tailwind CSS, Vercel, authentication/RBAC** |
| Core API | Python, PostgreSQL, SQL, schema design, REST concepts, Docker | **FastAPI, Redis (local queue), managed-Postgres deploy** |
| Agent core / runner | prompt engineering, LLM structured extraction, Python | **LangGraph, multi-agent architecture, Claude Agent SDK** (CrewAI only if B9 approved) |
| MCP mount | API contract design (PruTech), Python | **MCP** |
| RAG | ETL/data pipelines, data cleaning | **RAG, vector database, embeddings** |
| Evals | testing discipline (170 Playwright), root-cause habits | **LLM evals** |
| Analytics wing | Java (3 projects), SQL, OOP, Docker Compose | **Spring Boot, Kafka (via Redpanda's Kafka API), microservices, MySQL** |
| Automation | web scraping, workflow thinking (soybean admin flow) | **n8n, Slack API** (Zapier optional) |
| Infra/CI | Docker, Compose, CI/CD, Git/GitHub, Azure Pipelines patterns | GitHub Actions (Tier-2 confirm) |
| Stretch | — | **fine-tuning** (Colab, not local) |

Honesty note on the rev 2 trade: dropping paid API calls means **"OpenAI API"
cannot be claimed** (no real calls — don't claim it). "Anthropic" is earned as
*Claude Agent SDK + MCP integration*, which is at least as strong a line for
agent-role postings. Left honestly unanswered: Angular, Salesforce,
Weblogic/Tomcat-class legacy, OpenAI API. Expected coverage: **16–17 of 23**,
plus Tier-2→Tier-1 upgrades (REST design, JSON/HTTP, React Router/SPA, RBAC,
GitHub workflows).

---

## 5. Phases, acceptance, and question unlocks

| Phase | Build | Done when | Questions unlocked |
|---|---|---|---|
| **0** (new — pure port, zero blockers) | Monorepo scaffold; port pool ETL, honesty guard, validators, deterministic tailor into `packages/shared`+`apps/api` with tests; local compose (pg+pgvector, redis) | Ported test suite green in the new repo; deterministic tailor of a real JD via local API | — (foundation) |
| **1** (weekend) | FastAPI + Postgres; MCP mount; runner skeleton + Agent SDK loop; LangGraph graph on the runner | Graph tailors a real JD end-to-end with **zero API spend**; Claude connects via the one-liner and drives it | FastAPI, LangGraph, multi-agent, MCP, Claude Agent SDK |
| **2** | Next.js/Tailwind UI + JWT/RBAC (proxy pattern §2.1); deploy Vercel + Neon + free container host | Live URL, login works, pipeline board renders from the API; runner-offline badge works | Next.js, Tailwind, Vercel, authentication |
| **3** | pgvector RAG (fastembed) + eval harness; CrewAI comparison only if B9 approved | Retrieval evals reported; eval scoreboard live | RAG, vector DB, embeddings, LLM evals (CrewAI only with B9) |
| **4** | JDK 21 install; n8n + Slack; Spring Boot/Redpanda/MySQL analytics wing (local compose) | Slack DM fires on job-add; funnel stats served from MySQL | n8n, Slack API, Spring Boot, Kafka, microservices, MySQL |
| **5** (stretch) | LoRA fine-tune + eval delta; optional agent-browser applier | Eval shows measurable delta | fine-tuning |

After each phase: answer the unlocked questions on the Apply tab with one-line
evidence ("built the MCP mount in CareerPilot exposing 7 tools"), verify against
the repo, fold into the career record, re-tailor everything.

---

## 6. Non-negotiables carried over

- **NO PAID API CALLS, EVER** — now a CareerPilot rule too, not just the
  applier's. No API-key code paths; subscription (Agent SDK/MCP) and local
  models only. CI makes zero LLM calls.
- Truthful content only (retrieval-bounded tailoring, ported honesty guard as a
  hard eval metric); human confirm before any submission; rate caps on any
  automated applying; no CAPTCHA/bot-check circumvention; credentials never in
  code (env/vault).

---

## 7. Designed-in fixes for known breakage points

Every gap identified in the rev 1 review now has its fix in the architecture —
nothing on this list is left to be discovered at deploy time.

| # | Would have broken | Why | Fix now designed in |
|---|---|---|---|
| 7.1 | Resume rendering on the deployed host | Word COM is Windows-only; render pipeline can't run on Linux containers | Rendering is a **runner** duty (§2.3) — it runs on the exact machine where Word COM is already proven. Deployed API only stores/serves artifacts. |
| 7.2 | Rendered files vanishing after deploys | Free-tier hosts have ephemeral filesystems | Artifacts stored as bytea in Postgres (§3) — no object-storage account needed at this scale. |
| 7.3 | LLM features dead in production | A hosted API can't reach a local Ollama, and API keys are banned | The deployed API is deterministic-by-design; intelligence is an async quality pass via the runner + Max plan (§1, §2.3). Runner offline → badge, not breakage. |
| 7.4 | Login breaking in browsers | httpOnly cookies between `*.vercel.app` and the API host are third-party cookies — blocked | Same-origin proxy through Next.js rewrites for REST; in-memory access token + rotating refresh; WS auth via token subprotocol (§2.1). |
| 7.5 | Analytics wing unbuildable | Machine has Java 8; Spring Boot 3 needs 17+ | JDK 21 (Temurin) install is an explicit Phase 4 prerequisite; wing is local-compose-only; Redpanda replaces full Kafka (§2.7). |
| 7.6 | UI referencing fields the schema lacked | rev 1 `jobs` had no fit/missing-keyword columns and no status history | `fit_score`, `missing_keywords`, `status_events` added to the data model (§3). |
| 7.7 | CI flaking/failing on LLM access | Judge metrics need a model; CI has no subscription | CI gates are fully deterministic; LLM-judge runs as runner batch jobs (§2.6). |
| 7.8 | Embeddings blocked on Ollama install | rev 1 defaulted embeddings to Ollama, which isn't installed | In-process fastembed/bge-small — pip install, CPU, runs in CI and prod (§2.5). |
| 7.9 | CrewAI needing an API endpoint | No API credits, wrapping subscription auth as a generic endpoint is off-limits, and local models are ruled out by the lightweight rule | Benchmark deferred by default and CrewAI not claimed; optional free hosted tier unlocks it (B9) (§2.3). |
| 7.10 | Core deploy depending on Kafka/Redis add-ons | Kafka in prod is disproportionate; every add-on is another account/cost | Outbox pattern with no-op relay; Postgres-backed queue + rate ledger in prod; Redis stays a local-compose skill (§2.2, §2.7). |

---

## 8. Prerequisites & blockers (who owes what, and what it blocks)

**Nothing blocks Phase 0.** It is pure porting of code that already exists and
passes 105 tests in this repo.

### Dhiren's decisions/accounts (Claude cannot create accounts — hard rule)

| # | Item | Blocks | Effort / cost | Notes |
|---|---|---|---|---|
| B1 | Create the GitHub repo (name, public/private) | first commit of Phase 0 | 5 min / free | Recommend public from day one *if* B2 is resolved first |
| B2 | **Privacy call: real career data vs sanitized demo data** in the public repo + deployed instance | schema details (redaction), repo visibility, viewer share link | decision only | The seed data is real PII (contact info, employers, dates). Recommendation: real data in his private deployment; a sanitized fictional dataset committed to the repo as the demo seed. `redact_for_viewer` flag (§3) covers the share-link case either way. |
| B3 | Vercel account + connect repo | Phase 2 deploy | 10 min / free | |
| B4 | Neon account (Postgres + pgvector) | Phase 2 deploy | 10 min / free | Free tier includes pgvector; avoids paying for Railway Postgres |
| B5 | Container host for the API (Render free tier or Fly.io) | Phase 2 deploy | 15 min / free | Free tiers cold-start (~30 s after idle) — acceptable for a demo; ~$5/mo on Railway buys always-on if he prefers |
| B6 | Confirm Max-plan headroom for runner batches | Phase 1 quality passes | decision only | Runner draws on the same plan as interactive sessions; nightly batching + queue backoff keeps it polite. No dollars involved. |
| B7 | JDK 21 (Temurin) install | Phase 4 analytics wing | 10 min, winget | Claude can run the install with permission when Phase 4 starts |
| B8 | Slack workspace + bot app token | Phase 4 automation | 20 min / free | |
| B9 | Free hosted-tier model account (Groq or Google AI Studio free quota) for the one-off CrewAI benchmark | Phase 3 CrewAI claim only | 15 min / $0 | Optional — default is to skip the benchmark and not claim CrewAI. Local models are ruled out by the lightweight rule. |
| B10 | Colab account | Phase 5 stretch | free | Optional |

### Accepted constraints (not blockers — acknowledged trade-offs)

- **Quality passes only run when Dhiren's PC runs the runner.** Deterministic
  results are always instant; the badge makes the gap visible instead of silent.
- **Max-plan rate limits** bound runner throughput; the queue absorbs bursts.
- **Free-tier cold starts** (~30 s) on the API host after idle periods.
- **"OpenAI API" is not claimable** under the zero-spend rule (see §4).
- **Nothing heavy runs locally:** no local LLMs or GPU work, ever; the compose
  stacks (analytics, n8n) are demo-time only — started for a demo, stopped after.
