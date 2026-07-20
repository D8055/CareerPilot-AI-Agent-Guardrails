# apps/web — CareerPilot UI (Phase 2)

Next.js (App Router) + TypeScript + Tailwind v4. Pipeline board, job detail,
career record, evals, and settings (with the "Connect Claude" MCP one-liner).
See spec §2.1.

## Run

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # production build (must pass)
```

Point it at the API with `NEXT_PUBLIC_API_URL` (defaults to
`http://127.0.0.1:8000`). Start the API from the repo root:

```powershell
$env:CAREERPILOT_OWNER_PASSWORD='devpass123'
.venv\Scripts\uvicorn main:app --app-dir apps/api --port 8000
```

## How it's put together

- `lib/api.ts` — fetch wrapper; bearer token kept in memory with
  sessionStorage persistence; any 401 clears the session and redirects to
  `/login`. `lib/types.ts` mirrors the API contract.
- `lib/hooks.ts` — `useApi` (fetch + refetch) and `useLive` (WebSocket
  `/ws` auto-refresh with a 15s polling backstop).
- `components/` — shell/nav, theme toggle, and the shared instrument set
  (match gauge, status/tier/quality chips, timestamps).
- `app/(app)/*` — authenticated pages behind the shared shell; `app/login`
  stands alone.
- Roles: `owner` sees mutating controls (add job, tailor, status, blockers,
  evals run, share); `viewer` is read-only.

## Design notes

Dark-first "night flight deck": IBM Plex Sans/Mono + Space Grotesk,
EFIS-style magenta for owner actions and active nav, amber reserved as the
caution color (flagged keywords, waiting-on-Dhiren, pending quality passes).
Theme follows the system by default; the header toggle overrides via a
`dark` class persisted in localStorage. Tokens live in `app/globals.css`.
