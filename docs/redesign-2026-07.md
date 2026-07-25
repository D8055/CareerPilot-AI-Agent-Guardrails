# Redesign spec — July 2026 (Dhiren's request, refined by tracker research)

Research base: Huntr (kanban, drag-and-drop, Saved→Applied→Interviewing→Offer,
minimal card faces, details behind a click) and Teal (table view with a pipeline
summary strip). CareerPilot mirrors those conventions.

## Product principle: three steps, max
Every user flow completes in at most 3 actions. Enforced flows:
- Get running: download → `start.cmd` → log in. (start.cmd now boots API, web,
  AND the runner — recruiter scores need zero extra setup.)
- Add a job: New Jobs → paste URL → Add.
- Apply (begin tailoring): New Jobs → Apply. (Bulk: select → Apply all.)
- Get a resume: job page → pick 1/2 page → Generate.

## Navigation
`New Jobs · Board · Career · Settings`. Evals page removed (its gates still run
in CI and the API; it was a builder tool, not a job-seeker tool). No arrow
glyphs in tab/table headers (sort state is aria-only).

## New Jobs tab (the "Saved" stage, Huntr convention)
- List of jobs not yet in the pipeline (status `new`, incl. legacy
  discovered/enriched). Row: company · role · match (if scored) · Apply button ·
  select checkbox.
- Selecting ≥1 shows a bulk bar: "Apply all (n)" and "Delete (n)" (confirm).
- Apply ONLY begins tailoring (never submits anything anywhere); on success the
  job moves to the Board's Tailored column.
- Add-job (URL-only + auto-enrich) lives here; new jobs stay in New Jobs until
  applied, matching the Saved-stage convention.

## Board tab (Huntr-style kanban + Teal-style summary)
- Pipeline summary strip on top (stage counts).
- Columns: Tailored → Applied → Interview → Offer, Rejected last and muted.
- Cards show ONLY: company, role, match gauge. Details live on the job page.
- Drag a card between columns to change status (research-standard interaction);
  falls back to the job-page status dropdown.
- Table view stays as the alternate (Teal pattern): Company · Role · Status ·
  Match · Added. No visible sort arrows.

## Oreo theme (both modes, still switchable)
- Dark ("cookie"): near-black charcoal surfaces, cream text and accents.
- Light ("cream"): cream background, white panels, near-black ink and accents.
- Amber keeps its semantic meaning (needs a human) in both modes.

## Career page
- Every item gets inline editing (pencil → textarea → Save). Pool-sourced items
  write back to the private pool YAML (single source of truth) and re-embed;
  owner-added items update directly. Honesty unchanged: editing your record is
  the owner asserting facts, same as adding.

## Data reset
Existing jobs reset to `new` (plans/artifacts/passes cleared) so everything
starts in New Jobs.

## Problems the research surfaced (fixed alongside)
1. No delete existed anywhere — trackers all have remove/archive. Added
   DELETE /jobs/{id} + bulk delete.
2. Cards were overloaded (ats/channel/flagged/added chips) vs Huntr's minimal
   faces — cut to 3 fields.
3. No drag-and-drop — the defining kanban interaction. Added.
4. Recruiter scores required manually starting a third process — violated the
   3-step rule. start.cmd/stop.cmd now manage the runner too (B6 resolved).
5. Jobs skipped the "Saved" stage and landed straight in the pipeline. New Jobs
   tab restores the standard funnel.
