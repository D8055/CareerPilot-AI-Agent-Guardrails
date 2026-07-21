"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, isOwner } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type {
  JobDetail,
  PlanFull,
  PlanMeta,
  TailoredResume,
  TailorResult,
} from "@/lib/types";
import {
  ErrorNote,
  Eyebrow,
  Loading,
  MatchGauge,
  QualityBadge,
  StatusChip,
  fmtDate,
} from "@/components/ui";

const STATUSES = [
  "discovered",
  "tailored",
  "applied",
  "interview",
  "offer",
  "rejected",
];

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const owner = isOwner();

  const job = useApi(useCallback(() => api<JobDetail>(`/jobs/${id}`), [id]));
  const [plan, setPlan] = useState<PlanFull | null>(null);
  const [tailorResult, setTailorResult] = useState<TailorResult | null>(null);

  // Full plan is optional: a job with no plan yet 404s here, which is fine.
  useEffect(() => {
    let cancelled = false;
    api<PlanFull>(`/jobs/${id}/plan`)
      .then((p) => {
        if (!cancelled) setPlan(p);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id, job.data?.plans?.length]);

  if (job.loading) return <Loading label="Reading the job" />;
  if (job.error) return <ErrorNote message={job.error} />;
  if (!job.data) return null;

  const j = job.data;
  const latestPlan: PlanMeta | undefined = [...(j.plans ?? [])].sort((a, b) =>
    String(b.created_at).localeCompare(String(a.created_at))
  )[0];

  const matchScore = tailorResult?.match_score ?? j.match;
  const matched = tailorResult?.matched_keywords ?? j.matched_keywords ?? [];
  const missing = tailorResult?.missing_keywords ?? j.missing_keywords ?? [];

  return (
    <div className="flex flex-col gap-6">
      {/* ---- header ---- */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Eyebrow>
            {j.ats || "ats tbd"} · {j.channel || "channel tbd"}
          </Eyebrow>
          <h1 className="display mt-1 text-2xl font-bold leading-tight">
            {j.company}
          </h1>
          <p className="text-dim">{j.role}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusChip status={j.status} />
            {j.url && (
              <a
                href={j.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-accent underline underline-offset-2"
              >
                View posting ↗
              </a>
            )}
          </div>
        </div>
        <div className="flex flex-col items-center gap-1">
          <MatchGauge score={matchScore} size={72} />
          <Eyebrow>match</Eyebrow>
        </div>
      </header>

      {owner && <StatusEditor id={String(id)} current={j.status} onSaved={() => job.refetch()} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="flex flex-col gap-6 lg:col-span-3">
          {/* ---- keywords ---- */}
          <section className="panel p-5">
            <h2 className="display mb-3 text-base font-semibold">Keywords</h2>
            <div className="flex flex-col gap-3">
              <div>
                <Eyebrow>matched</Eyebrow>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {matched.length === 0 ? (
                    <span className="text-xs text-faint">
                      No matched keywords recorded — run tailor to compute them.
                    </span>
                  ) : (
                    matched.map((k) => (
                      <span key={k} className="chip chip-green">
                        {k}
                      </span>
                    ))
                  )}
                </div>
              </div>
              <div>
                <Eyebrow>missing — flagged, never added</Eyebrow>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {missing.length === 0 ? (
                    <span className="text-xs text-faint">Nothing flagged.</span>
                  ) : (
                    missing.map((k) => (
                      <span
                        key={k}
                        className="chip chip-amber"
                        title="This JD keyword is not in the career record. It is flagged for Dhiren, never written into the resume."
                      >
                        ⚑ {k}
                      </span>
                    ))
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* ---- plan ---- */}
          <section className="panel p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="display text-base font-semibold">Latest plan</h2>
              {latestPlan && <QualityBadge value={latestPlan.quality_pass} long />}
            </div>
            {latestPlan ? (
              <div className="flex flex-col gap-3">
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {latestPlan.summary_text}
                </p>
                <div className="readout text-[0.65rem] text-faint">
                  by {latestPlan.created_by} · {fmtDate(latestPlan.created_at)}
                </div>
                {plan?.honesty_report != null &&
                  !(Array.isArray(plan.honesty_report) && plan.honesty_report.length === 0) && (
                  <details>
                    <summary className="cursor-pointer text-xs font-semibold text-dim">
                      Honesty report
                    </summary>
                    <pre className="readout mt-2 max-h-56 overflow-auto rounded-lg bg-panel2 p-3 text-[0.7rem] leading-relaxed">
                      {typeof plan.honesty_report === "string"
                        ? plan.honesty_report
                        : JSON.stringify(plan.honesty_report, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ) : (
              <p className="text-sm text-faint">
                No plan yet. Paste the JD below and run tailor.
              </p>
            )}
          </section>

          {/* ---- tailored resume ---- */}
          {latestPlan && <ResumeView id={String(id)} planStamp={latestPlan.id} />}

          {/* ---- JD ---- */}
          <section className="panel p-5">
            <h2 className="display mb-3 text-base font-semibold">Job description</h2>
            {j.jd_text ? (
              <pre className="readout max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-panel2 p-3 text-[0.75rem] leading-relaxed">
                {j.jd_text}
              </pre>
            ) : (
              <p className="text-sm text-faint">No JD text stored for this job yet.</p>
            )}
          </section>
        </div>

        <div className="flex flex-col gap-6 lg:col-span-2">
          {owner && (
            <TailorPanel
              id={String(id)}
              initialJd={j.jd_text ?? ""}
              onResult={(r) => {
                setTailorResult(r);
                job.refetch();
              }}
            />
          )}

          {/* ---- timeline ---- */}
          <section className="panel p-5">
            <h2 className="display mb-3 text-base font-semibold">Status timeline</h2>
            {(j.status_events ?? []).length === 0 ? (
              <p className="text-sm text-faint">No status changes recorded.</p>
            ) : (
              <ol className="relative flex flex-col gap-4 border-l border-line pl-4">
                {[...j.status_events]
                  .sort((a, b) => String(b.ts).localeCompare(String(a.ts)))
                  .map((ev, i) => (
                    <li key={`${ev.ts}-${i}`} className="relative">
                      <span
                        className="absolute -left-[1.32rem] top-1.5 h-2 w-2 rounded-full"
                        style={{
                          background: i === 0 ? "var(--accent)" : "var(--line-strong)",
                        }}
                        aria-hidden
                      />
                      <div className="flex items-center gap-2">
                        <StatusChip status={ev.status} />
                        <span className="readout text-[0.65rem] text-faint">
                          {fmtDate(ev.ts)}
                        </span>
                      </div>
                      {ev.note && <p className="mt-1 text-xs text-dim">{ev.note}</p>}
                    </li>
                  ))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function StatusEditor({
  id,
  current,
  onSaved,
}: {
  id: string;
  current: string;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(current);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/jobs/${id}/status`, {
        method: "PATCH",
        body: { status, note: note || null },
      });
      setNote("");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update status.");
    } finally {
      setBusy(false);
    }
  }

  const options = STATUSES.includes(current) ? STATUSES : [current, ...STATUSES];

  return (
    <form onSubmit={submit} className="panel flex flex-wrap items-end gap-3 p-4">
      <label className="flex flex-col gap-1">
        <span className="eyebrow">Status</span>
        <select
          className="select w-44"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {options.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-40 flex-1 flex-col gap-1">
        <span className="eyebrow">Note (optional)</span>
        <input
          className="input"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. recruiter replied"
        />
      </label>
      <button
        type="submit"
        className="btn btn-primary"
        disabled={busy || (status === current && !note)}
      >
        {busy ? "Saving…" : "Save status"}
      </button>
      {error && <p className="w-full text-sm text-red">{error}</p>}
    </form>
  );
}

function TailorPanel({
  id,
  initialJd,
  onResult,
}: {
  id: string;
  initialJd: string;
  onResult: (r: TailorResult) => void;
}) {
  const [jd, setJd] = useState(initialJd);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TailorResult | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<TailorResult>(`/jobs/${id}/tailor`, {
        method: "POST",
        body: { jd_text: jd },
      });
      setResult(r);
      onResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tailor run failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-5">
      <h2 className="display mb-1 text-base font-semibold">Tailor</h2>
      <p className="mb-3 text-xs text-dim">
        Deterministic keyword match against the career record. Missing keywords
        are flagged for Dhiren, never invented.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <textarea
          className="textarea min-h-40"
          placeholder="Paste the job description here"
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          required
        />
        <button type="submit" className="btn btn-primary self-start" disabled={busy}>
          {busy ? "Tailoring…" : "Run tailor"}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
      {result && (
        <div className="mt-3 flex flex-col gap-2 rounded-lg bg-panel2 p-3">
          <div className="flex items-center gap-3">
            <MatchGauge score={result.match_score} size={44} />
            <div className="flex flex-col">
              <span className="readout text-sm font-semibold">
                {result.match_score}% match
              </span>
              <QualityBadge value={result.quality_pass} />
            </div>
          </div>
          <div className="readout text-[0.7rem] text-dim">
            {result.matched_keywords.length} matched ·{" "}
            <span className="text-amber">{result.missing_keywords.length} flagged</span>
          </div>
        </div>
      )}
    </section>
  );
}

function ResumeView({ id, planStamp }: { id: string; planStamp: number | string }) {
  const [data, setData] = useState<TailoredResume | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<TailoredResume>(`/jobs/${id}/resume`)
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [id, planStamp]);

  if (error) return null;
  if (!data) return null;
  const r = data.resume;
  const contactLine = [r.contact.location, r.contact.phone, r.contact.email,
    r.contact.linkedin].filter(Boolean).join("  ·  ");

  return (
    <section className="panel p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="display text-base font-semibold">Tailored resume</h2>
        <span className="readout text-[0.65rem] text-faint">
          content preview · docx rendering arrives with the runner
        </span>
      </div>
      {/* deliberately paper-colored in both themes — it is a document */}
      <div className="rounded-lg border border-[var(--line)] bg-white px-8 py-7 font-serif text-[0.85rem] leading-relaxed text-neutral-900 shadow-sm">
        <div className="text-center">
          <div className="text-lg font-bold tracking-wide">{r.contact.name}</div>
          <div className="mt-0.5 text-[0.75rem] text-neutral-600">{contactLine}</div>
        </div>

        <ResumeRule label="Summary" />
        <p>{r.summary}</p>

        <ResumeRule label="Skills" />
        {r.skills.map((g) => (
          <p key={g.label} className="mb-0.5">
            <span className="font-semibold">{g.label}:</span> {g.items.join(", ")}
          </p>
        ))}

        <ResumeRule label="Experience" />
        {r.experience.map((role) => (
          <div key={role.org} className="mb-2.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="font-semibold">{role.org}</span>
              <span className="text-[0.75rem] text-neutral-600">{role.dates}</span>
            </div>
            <div className="italic">{role.title}</div>
            <ul className="mt-1 list-disc pl-5">
              {role.bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
        ))}

        <ResumeRule label="Projects" />
        {r.projects.map((p) => (
          <div key={p.name} className="mb-2.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="font-semibold">{p.name}</span>
              <span className="text-[0.75rem] text-neutral-600">{p.stack}</span>
            </div>
            <ul className="mt-1 list-disc pl-5">
              {p.bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
        ))}

        {r.accomplishments.length > 0 && (
          <>
            <ResumeRule label="Accomplishments" />
            <ul className="list-disc pl-5">
              {r.accomplishments.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}

function ResumeRule({ label }: { label: string }) {
  return (
    <div className="mb-1.5 mt-4 border-b border-neutral-300 pb-0.5 text-[0.7rem] font-bold uppercase tracking-[0.14em] text-neutral-700">
      {label}
    </div>
  );
}
