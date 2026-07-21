"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, apiDownload, isOwner } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type {
  Attention,
  AttentionItem,
  Job,
  Question,
  Runner,
  Stats,
} from "@/lib/types";
import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Loading,
  MatchGauge,
  StatusChip,
  fmtWhen,
} from "@/components/ui";

const COLUMNS = [
  "discovered",
  "tailored",
  "applied",
  "interview",
  "offer",
  "rejected",
];

export default function Dashboard() {
  const owner = isOwner();

  const jobs = useApi(useCallback(() => api<Job[]>("/jobs"), []));
  const stats = useApi(useCallback(() => api<Stats>("/stats"), []));
  const runners = useApi(useCallback(() => api<Runner[]>("/status/runners"), []));
  const questions = useApi(useCallback(() => api<Question[]>("/questions"), []));
  const attention = useApi(useCallback(() => api<Attention>("/attention"), []));

  const refreshAll = useCallback(() => {
    jobs.refetch();
    stats.refetch();
    runners.refetch();
    questions.refetch();
    attention.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.refetch, stats.refetch, runners.refetch, questions.refetch, attention.refetch]);

  // Board | Table — persisted per browser; read after mount so SSR matches.
  const [view, setView] = useState<"board" | "table">("board");
  useEffect(() => {
    if (localStorage.getItem("cp_pipeline_view") === "table") setView("table");
  }, []);
  const pickView = useCallback((v: "board" | "table") => {
    setView(v);
    localStorage.setItem("cp_pipeline_view", v);
  }, []);

  const wsOpen = useLive(refreshAll);

  const runnerOnline = (runners.data ?? []).some((r) => r.online);

  const byColumn: Record<string, Job[]> = {};
  const extras: string[] = [];
  for (const job of jobs.data ?? []) {
    const col = COLUMNS.includes(job.status) ? job.status : job.status;
    if (!COLUMNS.includes(col) && !extras.includes(col)) extras.push(col);
    (byColumn[col] ??= []).push(job);
  }
  const allColumns = [...COLUMNS, ...extras];

  return (
    <div className="flex flex-col gap-6">
      {/* ---- instrument cluster ---- */}
      <section aria-label="Pipeline stats">
        <div className="panel px-5 py-4">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
            <Readout label="Jobs" value={stats.data?.jobs_total} />
            <Readout label="Plans" value={stats.data?.plans} />
            <Readout label="Open questions" value={stats.data?.open_questions} />
            <Readout label="QC pending" value={stats.data?.quality_passes_pending} />

            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Link
                href="/settings"
                className="chip chip-amber !text-[0.75rem] !px-3 !py-1.5 font-semibold hover:brightness-110"
                title="Open blockers in Settings"
              >
                Waiting on Dhiren: {stats.data?.waiting_on_dhiren ?? "–"}
              </Link>
              {runners.data &&
                (runnerOnline ? (
                  <span className="chip chip-green">
                    <span className="pulse inline-block h-1.5 w-1.5 rounded-full bg-green" />
                    runner online
                  </span>
                ) : (
                  <span className="chip chip-amber">
                    quality passes paused — runner offline
                  </span>
                ))}
              <span
                className="chip"
                title={wsOpen ? "Live via WebSocket" : "Refreshing every 15s"}
              >
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    wsOpen ? "pulse bg-cyan" : "bg-faint"
                  }`}
                />
                {wsOpen ? "live" : "polling"}
              </span>
            </div>
          </div>
        </div>
        <div className="ruler mx-3 mt-1" aria-hidden />
      </section>

      {stats.error && <ErrorNote message={stats.error} />}
      {jobs.error && !stats.error && <ErrorNote message={jobs.error} />}

      {/* ---- pipeline board ---- */}
      <section aria-label="Pipeline board" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="display text-lg font-semibold">Pipeline</h1>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <ViewToggle view={view} onChange={pickView} />
            <ExportCsv />
            {owner && <AddJob onAdded={refreshAll} />}
          </div>
        </div>

        {jobs.loading ? (
          <Loading label="Reading the pipeline" />
        ) : (jobs.data ?? []).length === 0 ? (
          <EmptyState>
            No jobs on the board yet. Add one above, or push one through the
            API or a connected MCP client.
          </EmptyState>
        ) : view === "table" ? (
          <JobsTable jobs={jobs.data ?? []} />
        ) : (
          <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6">
            <div className="flex min-w-max gap-3">
              {allColumns.map((col) => {
                const items = byColumn[col] ?? [];
                if (items.length === 0 && !COLUMNS.includes(col)) return null;
                return (
                  <div key={col} className="w-60 shrink-0">
                    <div className="mb-2 flex items-baseline justify-between px-1">
                      <Eyebrow>{col}</Eyebrow>
                      <span className="readout text-xs text-faint">
                        {items.length}
                      </span>
                    </div>
                    <div className="flex flex-col gap-2">
                      {items.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-line px-3 py-4 text-center text-xs text-faint">
                          empty
                        </div>
                      ) : (
                        items.map((job) => <JobCard key={job.id} job={job} />)
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* ---- items that need a human ---- */}
      <AttentionPanel
        items={attention.data?.items ?? []}
        owner={owner}
        onChanged={refreshAll}
      />

      {/* ---- open questions ---- */}
      <QuestionsPanel
        questions={questions.data}
        error={questions.error}
        owner={owner}
        onAnswered={refreshAll}
      />
    </div>
  );
}

function Readout({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex flex-col">
      <span className="eyebrow">{label}</span>
      <span className="readout text-2xl font-semibold leading-tight">
        {value ?? "–"}
      </span>
    </div>
  );
}

function ViewToggle({
  view,
  onChange,
}: {
  view: "board" | "table";
  onChange: (v: "board" | "table") => void;
}) {
  return (
    <div
      className="readout flex items-center gap-0.5 rounded-lg border border-line bg-panel p-0.5 text-[0.7rem]"
      role="group"
      aria-label="Pipeline view"
    >
      {(["board", "table"] as const).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={view === v}
          onClick={() => onChange(v)}
          className={`rounded-md px-2.5 py-1 font-semibold uppercase tracking-wide transition-colors ${
            view === v ? "bg-panel2 text-ink" : "text-faint hover:text-ink"
          }`}
        >
          {v}
        </button>
      ))}
    </div>
  );
}

function ExportCsv() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <button
        type="button"
        className="btn"
        disabled={busy}
        title={error ?? "Download every job as CSV"}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await apiDownload("/export/jobs.csv", "careerpilot_jobs.csv");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Export failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Exporting…" : "Export CSV"}
      </button>
      {error && <span className="text-xs text-red">{error}</span>}
    </>
  );
}

/* ---- table view ---- */

type SortKey = "company" | "role" | "status" | "match" | "channel" | "added_at";

const TABLE_COLS: { key: SortKey; label: string }[] = [
  { key: "company", label: "Company" },
  { key: "role", label: "Role" },
  { key: "status", label: "Status" },
  { key: "match", label: "Match" },
  { key: "channel", label: "Channel" },
  { key: "added_at", label: "Added" },
];

function compareJobs(a: Job, b: Job, key: SortKey): number {
  if (key === "match") return (a.match ?? -1) - (b.match ?? -1);
  const av = String(a[key] ?? "").toLowerCase();
  const bv = String(b[key] ?? "").toLowerCase();
  return av.localeCompare(bv);
}

function JobsTable({ jobs }: { jobs: Job[] }) {
  const router = useRouter();
  const [sortKey, setSortKey] = useState<SortKey>("added_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function clickHeader(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "match" || key === "added_at" ? "desc" : "asc");
    }
  }

  const sorted = [...jobs].sort((a, b) => {
    const c = compareJobs(a, b, sortKey);
    return sortDir === "asc" ? c : -c;
  });

  return (
    <div className="panel overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line">
            {TABLE_COLS.map((col) => (
              <th
                key={col.key}
                className="px-4 py-2.5 text-left"
                aria-sort={
                  sortKey === col.key
                    ? sortDir === "asc"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                <button
                  type="button"
                  className="eyebrow cursor-pointer transition-colors hover:!text-[var(--ink)]"
                  onClick={() => clickHeader(col.key)}
                >
                  {col.label}
                  {sortKey === col.key && (sortDir === "asc" ? " ▲" : " ▼")}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--line)]">
          {sorted.map((job) => (
            <tr
              key={job.id}
              className="cursor-pointer transition-colors hover:bg-panel2"
              onClick={() => router.push(`/jobs/${job.id}`)}
            >
              <td className="px-4 py-2.5 font-semibold">
                <Link
                  href={`/jobs/${job.id}`}
                  className="hover:text-accent"
                  onClick={(e) => e.stopPropagation()}
                >
                  {job.company}
                </Link>
              </td>
              <td className="px-4 py-2.5 text-dim">{job.role}</td>
              <td className="px-4 py-2.5">
                <StatusChip status={job.status} />
              </td>
              <td className="px-4 py-2.5">
                <MatchGauge score={job.match} size={32} />
              </td>
              <td className="px-4 py-2.5">
                {job.channel ? (
                  <span className="chip">{job.channel}</span>
                ) : (
                  <span className="text-faint">—</span>
                )}
              </td>
              <td className="readout px-4 py-2.5 text-xs text-faint">
                {fmtWhen(job.added_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---- attention: failed passes & fetches that need a human ---- */

function AttentionPanel({
  items,
  owner,
  onChanged,
}: {
  items: AttentionItem[];
  owner: boolean;
  onChanged: () => void;
}) {
  if (items.length === 0) return null;
  return (
    <section aria-label="Attention" className="flex flex-col gap-3">
      <h2 className="display text-lg font-semibold">Attention</h2>
      <div className="flex flex-col gap-2">
        {items.map((item, i) => (
          <AttentionRow
            key={`${item.type}-${item.intelligence_id ?? item.job_id}-${i}`}
            item={item}
            owner={owner}
            onChanged={onChanged}
          />
        ))}
      </div>
    </section>
  );
}

function AttentionRow({
  item,
  owner,
  onChanged,
}: {
  item: AttentionItem;
  owner: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    setNote(null);
    try {
      await fn();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="panel border-[color-mix(in_srgb,var(--amber)_45%,transparent)] px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">{item.company}</span>
            <span className="chip chip-amber">
              {item.type === "quality_failed" ? "quality pass failed" : "fetch failed"}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-dim">{item.detail}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {item.type === "enrich_failed" && (
            <>
              {owner && (
                <button
                  type="button"
                  className="btn px-2.5 py-1 text-xs"
                  disabled={busy !== null}
                  onClick={() =>
                    run("retry", async () => {
                      const res = await api<{ enrichment?: string }>(
                        `/jobs/${item.job_id}/enrich`,
                        { method: "POST" }
                      );
                      if (res.enrichment && res.enrichment.includes("failed")) {
                        setNote(res.enrichment);
                      }
                    })
                  }
                >
                  {busy === "retry" ? "Fetching…" : "Retry fetch"}
                </button>
              )}
              <Link href={`/jobs/${item.job_id}`} className="btn btn-quiet px-2.5 py-1 text-xs">
                Open job
              </Link>
            </>
          )}
          {item.type === "quality_failed" && owner && (
            <>
              <button
                type="button"
                className="btn px-2.5 py-1 text-xs"
                disabled={busy !== null || item.intelligence_id == null}
                onClick={() =>
                  run("retry", async () => {
                    await api(`/intelligence/${item.intelligence_id}/retry`, {
                      method: "POST",
                    });
                  })
                }
              >
                {busy === "retry" ? "Queuing…" : "Retry pass"}
              </button>
              <button
                type="button"
                className="btn btn-quiet px-2.5 py-1 text-xs"
                disabled={busy !== null || item.intelligence_id == null}
                onClick={() =>
                  run("dismiss", async () => {
                    await api(`/intelligence/${item.intelligence_id}/dismiss`, {
                      method: "POST",
                    });
                  })
                }
              >
                {busy === "dismiss" ? "Dismissing…" : "Dismiss"}
              </button>
            </>
          )}
        </div>
      </div>
      {note && <p className="mt-1.5 text-sm text-amber">{note}</p>}
      {error && <p className="mt-1.5 text-sm text-red">{error}</p>}
    </div>
  );
}

function JobCard({ job }: { job: Job }) {
  const flagged = (job.missing_keywords ?? []).length;
  return (
    <Link
      href={`/jobs/${job.id}`}
      className="panel block p-3 transition-colors hover:border-[var(--accent)]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{job.company}</div>
          <div className="truncate text-xs text-dim">{job.role}</div>
        </div>
        <MatchGauge score={job.match} size={38} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {job.ats && <span className="chip">{job.ats}</span>}
        {job.channel && <span className="chip">{job.channel}</span>}
        {flagged > 0 && (
          <span className="chip chip-amber" title="Missing JD keywords — flagged, never added">
            {flagged} flagged
          </span>
        )}
      </div>
      <div className="readout mt-2 text-[0.65rem] text-faint">
        added {fmtWhen(job.added_at)}
      </div>
    </Link>
  );
}

function AddJob({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [manual, setManual] = useState(false);
  const [form, setForm] = useState({
    url: "",
    company: "",
    role: "",
    channel: "",
    jd_text: "",
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const job = await api<{ enrichment?: string }>("/jobs", {
        method: "POST",
        body: form,
      });
      setForm({ url: "", company: "", role: "", channel: "", jd_text: "" });
      onAdded();
      if (job.enrichment && job.enrichment.includes("failed")) {
        // keep the panel open so the note is seen: the job exists, but the
        // JD needs a manual paste on its detail page
        setNotice(job.enrichment);
        setManual(false);
      } else {
        setOpen(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the job.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button type="button" className="btn" onClick={() => setOpen((v) => !v)}>
        {open ? "Close" : "Add job"}
      </button>
      {open && (
        <form
          onSubmit={submit}
          className="panel absolute right-0 z-10 mt-2 flex w-[min(36rem,88vw)] flex-col gap-3 p-4"
        >
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Posting URL</span>
            <input
              className="input"
              type="url"
              required
              autoFocus
              placeholder="https://…"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
            />
          </label>
          <p className="text-xs text-faint">
            Company, role, and the job description are fetched from the page
            automatically. Sites that block fetching (LinkedIn does) still get
            added — you just paste the JD on the job page afterward.
          </p>
          {!manual && (
            <button
              type="button"
              className="self-start text-xs text-faint underline-offset-2 hover:underline"
              onClick={() => setManual(true)}
            >
              Enter details manually instead
            </button>
          )}
          {manual && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className="eyebrow">Company</span>
                  <input
                    className="input"
                    value={form.company}
                    onChange={(e) => setForm({ ...form, company: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="eyebrow">Role</span>
                  <input
                    className="input"
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                  />
                </label>
              </div>
              <label className="flex flex-col gap-1">
                <span className="eyebrow">Job description text</span>
                <textarea
                  className="textarea min-h-24"
                  value={form.jd_text}
                  onChange={(e) => setForm({ ...form, jd_text: e.target.value })}
                />
              </label>
            </>
          )}
          {notice && <p className="text-sm text-amber">{notice}</p>}
          {error && <p className="text-sm text-red">{error}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>
              {notice ? "Done" : "Cancel"}
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Fetching…" : "Add job"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function QuestionsPanel({
  questions,
  error,
  owner,
  onAnswered,
}: {
  questions: Question[] | null;
  error: string | null;
  owner: boolean;
  onAnswered: () => void;
}) {
  const open = (questions ?? []).filter((q) => !q.answer);
  const answered = (questions ?? []).filter((q) => !!q.answer);

  if (error) return null; // stats strip already surfaces API trouble

  return (
    <section aria-label="Open questions" className="flex flex-col gap-3">
      <h2 className="display text-lg font-semibold">Questions for Dhiren</h2>
      {questions === null ? (
        <Loading label="Checking questions" />
      ) : open.length === 0 && answered.length === 0 ? (
        <EmptyState>No questions right now. Tailoring will raise one when the record can&apos;t answer a JD.</EmptyState>
      ) : (
        <div className="flex flex-col gap-2">
          {open.map((q) => (
            <QuestionRow key={q.id} q={q} owner={owner} onAnswered={onAnswered} />
          ))}
          {answered.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-faint">
                {answered.length} answered
              </summary>
              <div className="mt-2 flex flex-col gap-2">
                {answered.map((q) => (
                  <div key={q.id} className="panel px-4 py-3 opacity-70">
                    <div className="text-sm">{q.question ?? q.text}</div>
                    <div className="mt-1 text-xs text-dim">↳ {q.answer}</div>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </section>
  );
}

function QuestionRow({
  q,
  owner,
  onAnswered,
}: {
  q: Question;
  owner: boolean;
  onAnswered: () => void;
}) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/questions/${q.id}/answer`, {
        method: "POST",
        body: { answer },
      });
      onAnswered();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the answer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel px-4 py-3">
      <div className="text-sm">{q.question ?? q.text ?? `Question ${q.id}`}</div>
      {owner ? (
        <form onSubmit={submit} className="mt-2 flex gap-2">
          <input
            className="input"
            placeholder="Answer truthfully — this feeds the career record"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            required
          />
          <button type="submit" className="btn shrink-0" disabled={busy}>
            {busy ? "Saving…" : "Save answer"}
          </button>
        </form>
      ) : (
        <div className="mt-1 text-xs text-faint">Awaiting the owner&apos;s answer.</div>
      )}
      {error && <p className="mt-1 text-sm text-red">{error}</p>}
    </div>
  );
}
