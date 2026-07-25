"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, isOwner } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type {
  Attention,
  AttentionItem,
  Job,
  Question,
  Runner,
  Stats,
} from "@/lib/types";
import { displayMatch, isNewJob } from "@/lib/types";
import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Loading,
  MatchGauge,
} from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useConfirm } from "@/components/Confirm";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

export default function NewJobsPage() {
  useDocumentTitle("New Jobs");
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

  const wsOpen = useLive(refreshAll);

  const runnerOnline = (runners.data ?? []).some((r) => r.online);
  const allJobs = jobs.data ?? [];
  const newJobs = allJobs.filter(isNewJob);
  const pipelineCount = allJobs.length - newJobs.length;
  const openQuestions =
    stats.data?.open_questions ??
    (questions.data ?? []).filter((q) => !q.answer).length;

  return (
    <div className="flex flex-col gap-6">
      {/* ---- instrument cluster (simplified) ---- */}
      <section aria-label="Pipeline stats">
        <div className="panel px-5 py-4">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
            <Readout label="New" value={jobs.data ? newJobs.length : undefined} />
            <Readout
              label="In pipeline"
              value={jobs.data ? pipelineCount : undefined}
            />
            <Readout label="Questions" value={openQuestions} />

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

      {/* ---- new jobs list ---- */}
      <section aria-label="New jobs" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="display text-lg font-semibold">New Jobs</h1>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {owner && <AddJob onAdded={refreshAll} />}
          </div>
        </div>

        {jobs.loading ? (
          <Loading label="Reading new jobs" />
        ) : newJobs.length === 0 ? (
          <EmptyState>No new jobs. Paste a posting URL to add one.</EmptyState>
        ) : (
          <NewJobsList jobs={newJobs} owner={owner} onChanged={refreshAll} />
        )}
      </section>

      {/* ---- open questions ---- */}
      <QuestionsPanel
        questions={questions.data}
        error={questions.error}
        owner={owner}
        onAnswered={refreshAll}
      />

      {/* ---- items that need a human ---- */}
      <AttentionPanel
        items={attention.data?.items ?? []}
        owner={owner}
        onChanged={refreshAll}
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

/* ---- the "Saved" stage: select, apply (begin tailoring), delete ---- */

function NewJobsList({
  jobs,
  owner,
  onChanged,
}: {
  jobs: Job[];
  owner: boolean;
  onChanged: () => void;
}) {
  const { success, error: toastError } = useToast();
  const confirm = useConfirm();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  // drop selections for rows that left the list (applied or deleted)
  useEffect(() => {
    setSelected((prev) => {
      const ids = new Set(jobs.map((j) => String(j.id)));
      const next = new Set([...prev].filter((id) => ids.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [jobs]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /** Apply = POST /jobs/{id}/tailor — it only BEGINS tailoring. */
  async function applyOne(job: Job) {
    setBusy(true);
    try {
      await api(`/jobs/${job.id}/tailor`, { method: "POST" });
      success("Tailoring started — moved to Board");
      onChanged();
    } catch (err) {
      // usually a 400: no JD yet — the row links to the job page to paste it
      toastError(err instanceof Error ? err.message : "Could not start tailoring.");
    } finally {
      setBusy(false);
    }
  }

  async function applyAll() {
    const targets = jobs.filter((j) => selected.has(String(j.id)));
    setBusy(true);
    let ok = 0;
    let needJd = 0;
    for (const job of targets) {
      try {
        await api(`/jobs/${job.id}/tailor`, { method: "POST" });
        ok++;
      } catch {
        needJd++;
      }
    }
    setBusy(false);
    onChanged();
    const summary = [
      ok > 0 ? `${ok} tailored` : null,
      needJd > 0 ? `${needJd} need${needJd === 1 ? "s" : ""} a JD` : null,
    ]
      .filter(Boolean)
      .join(", ");
    if (needJd > 0) toastError(summary || "Nothing tailored");
    else success(summary || "Nothing selected");
  }

  async function deleteSelected() {
    const targets = jobs.filter((j) => selected.has(String(j.id)));
    if (
      !(await confirm({
        title: `Delete ${targets.length} job${targets.length === 1 ? "" : "s"}?`,
        body: "They leave CareerPilot entirely — plans and history included.",
        confirmLabel: "Delete",
        destructive: true,
      }))
    )
      return;
    setBusy(true);
    let ok = 0;
    let failed = 0;
    for (const job of targets) {
      try {
        await api(`/jobs/${job.id}`, { method: "DELETE" });
        ok++;
      } catch {
        failed++;
      }
    }
    setBusy(false);
    onChanged();
    if (failed > 0) toastError(`${ok} deleted, ${failed} failed`);
    else success(`${ok} deleted`);
  }

  return (
    <div className="flex flex-col gap-2">
      {selected.size > 0 && (
        <div
          className="panel slide-in flex flex-wrap items-center gap-3 border-[var(--line-strong)] px-4 py-2.5"
          role="toolbar"
          aria-label="Bulk actions"
        >
          <span className="readout text-xs font-semibold">
            {selected.size} selected
          </span>
          {owner && (
            <>
              <button
                type="button"
                className="btn btn-primary px-3 py-1 text-xs"
                disabled={busy}
                onClick={applyAll}
              >
                {busy ? "Working…" : "Apply all"}
              </button>
              <button
                type="button"
                className="btn btn-danger px-3 py-1 text-xs"
                disabled={busy}
                onClick={deleteSelected}
              >
                Delete
              </button>
            </>
          )}
          <button
            type="button"
            className="btn btn-quiet ml-auto px-2.5 py-1 text-xs"
            onClick={() => setSelected(new Set())}
          >
            Clear
          </button>
        </div>
      )}

      <div className="panel divide-y divide-[var(--line)]">
        {jobs.map((job) => (
          <NewJobRow
            key={job.id}
            job={job}
            owner={owner}
            busy={busy}
            checked={selected.has(String(job.id))}
            onToggle={() => toggle(String(job.id))}
            onApply={() => applyOne(job)}
          />
        ))}
      </div>
    </div>
  );
}

function NewJobRow({
  job,
  owner,
  busy,
  checked,
  onToggle,
  onApply,
}: {
  job: Job;
  owner: boolean;
  busy: boolean;
  checked: boolean;
  onToggle: () => void;
  onApply: () => void;
}) {
  const router = useRouter();
  const m = displayMatch(job);
  return (
    <div
      className="flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-panel2"
      onClick={() => router.push(`/jobs/${job.id}`)}
    >
      <input
        type="checkbox"
        className="tap h-4 w-4 shrink-0 accent-[var(--accent)]"
        aria-label={`Select ${job.company}`}
        checked={checked}
        onClick={(e) => e.stopPropagation()}
        onChange={onToggle}
      />
      <div className="min-w-0 flex-1">
        <Link
          href={`/jobs/${job.id}`}
          className="text-sm font-semibold hover:underline underline-offset-2"
          onClick={(e) => e.stopPropagation()}
        >
          {job.company}
        </Link>
        <div className="truncate text-xs text-dim">{job.role}</div>
      </div>
      <MatchGauge score={m.value} size={36} source={m.source} />
      {owner && (
        <button
          type="button"
          className="btn btn-primary shrink-0 px-3 py-1 text-xs"
          disabled={busy}
          title="Begin tailoring — the job moves to the Board's Tailored column"
          onClick={(e) => {
            e.stopPropagation();
            onApply();
          }}
        >
          Apply
        </button>
      )}
    </div>
  );
}

/* ---- add a job: URL-first, manual fallback ---- */

function AddJob({ onAdded }: { onAdded: () => void }) {
  const { success, error: toastError } = useToast();
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
      success("Job added");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the job.");
      toastError(err instanceof Error ? err.message : "Could not add the job.");
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
  const { success, error: toastError } = useToast();
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
      toastError(err instanceof Error ? err.message : "Action failed.");
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
                        toastError(res.enrichment);
                      } else {
                        success("Re-fetched");
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
                    success("Re-queued");
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
                    success("Dismissed");
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

/* ---- questions for Dhiren ---- */

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
  const { success, error: toastError } = useToast();
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ confirmed?: boolean }>(`/questions/${q.id}/answer`, {
        method: "POST",
        body: { answer },
      });
      onAnswered();
      success(res.confirmed ? "Confirmed — re-tailored" : "Saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the answer.");
      toastError(err instanceof Error ? err.message : "Could not save the answer.");
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
            aria-label="Your answer"
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
