"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, apiBlobUrl, apiDownload, isOwner } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type {
  JobDetail,
  PlanFull,
  PlanMeta,
  ResumePdfStatus,
  TailorResult,
} from "@/lib/types";
import { displayMatch } from "@/lib/types";
import {
  ErrorNote,
  Eyebrow,
  Loading,
  MatchGauge,
  QualityBadge,
  StatusChip,
  fmtDate,
} from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

const STATUSES = [
  "new",
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

  useDocumentTitle(job.data?.company || "Job");

  if (job.loading) return <Loading label="Reading the job" />;
  if (job.error) return <ErrorNote message={job.error} />;
  if (!job.data) return null;

  const j = job.data;
  const latestPlan: PlanMeta | undefined = [...(j.plans ?? [])].sort((a, b) =>
    String(b.created_at).localeCompare(String(a.created_at))
  )[0];

  // prefer the recruiter (LLM) score; else the freshest keyword score
  const dm = displayMatch(j);
  const matchScore = dm.source === "recruiter" ? dm.value
    : (tailorResult?.match_score ?? dm.value);
  const matchSource: "recruiter" | "keyword" =
    dm.source === "recruiter" ? "recruiter" : "keyword";
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
                View posting
              </a>
            )}
          </div>
        </div>
        <div className="flex flex-col items-center gap-1">
          <MatchGauge score={matchScore} size={72} source={matchSource} />
          <Eyebrow>{matchSource === "recruiter" ? "recruiter match" : "keyword match"}</Eyebrow>
        </div>
      </header>

      {j.llm_analysis && (
        <section className="panel p-5">
          <div className="mb-2 flex items-center gap-2">
            <h2 className="display text-base font-semibold">Recruiter review</h2>
            <span className="chip chip-accent text-[0.65rem]">from your quality pass</span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-dim">
            {j.llm_analysis}
          </p>
        </section>
      )}

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
  const { success, error: toastError } = useToast();
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
      success(`Status set to ${status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update status.");
      toastError(err instanceof Error ? err.message : "Could not update status.");
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
  const { success, error: toastError } = useToast();
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
      success(`Tailored — match ${r.match_score ?? "?"}%`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tailor run failed.");
      toastError(err instanceof Error ? err.message : "Tailor run failed.");
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
          aria-label="Job description"
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

type Variant = "onepage" | "twopage";

function ResumeView({ id, planStamp }: { id: string; planStamp: number | string }) {
  const owner = isOwner();
  const { success, error: toastError } = useToast();
  const [status, setStatus] = useState<ResumePdfStatus | null>(null);
  const [variant, setVariant] = useState<Variant>("twopage");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const st = await api<ResumePdfStatus>(`/jobs/${id}/resume/status`);
      setStatus(st);
      return st;
    } catch {
      setStatus(null);
      return null;
    }
  }, [id]);

  // whenever the selected variant (or plan) changes, load its cached PDF if any
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    (async () => {
      const st = await loadStatus();
      if (cancelled || !st?.variants[variant]?.rendered) {
        setPdfUrl(null);
        return;
      }
      try {
        url = await apiBlobUrl(`/jobs/${id}/resume.pdf?variant=${variant}`);
        if (!cancelled) setPdfUrl(url);
        else if (url) URL.revokeObjectURL(url);
      } catch {
        /* controls still render */
      }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [id, planStamp, variant, loadStatus]);

  async function render() {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ verified?: boolean; pages?: number }>(
        `/jobs/${id}/resume/render?variant=${variant}`,
        { method: "POST" }
      );
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
      setPdfUrl(null);
      const st = await loadStatus();
      if (st?.variants[variant]?.rendered) {
        setPdfUrl(await apiBlobUrl(`/jobs/${id}/resume.pdf?variant=${variant}`));
      }
      success(
        result.verified
          ? `${variant === "onepage" ? "1-page" : "2-page"} resume generated`
          : "Generated (page target not met)"
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rendering failed.");
      toastError(e instanceof Error ? e.message : "Rendering failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!status) return null;
  const vs = status.variants[variant];
  const filename = `${id}_resume_${variant}.pdf`;

  return (
    <section className="panel p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="display text-base font-semibold">Tailored resume</h2>
        <div className="flex flex-wrap items-center gap-2">
          {/* 1-page / 2-page toggle */}
          <div
            className="readout flex items-center gap-0.5 rounded-lg border border-line bg-panel p-0.5 text-[0.7rem]"
            role="group"
            aria-label="Resume length"
          >
            {(["onepage", "twopage"] as Variant[]).map((val) => (
              <button
                key={val}
                type="button"
                className={`rounded-md px-2.5 py-1 ${
                  variant === val ? "bg-accent text-bg" : "text-dim hover:text-ink"
                }`}
                aria-pressed={variant === val}
                onClick={() => setVariant(val)}
              >
                {val === "onepage" ? "1 page" : "2 page"}
              </button>
            ))}
          </div>
          {vs.rendered && vs.stale && (
            <span className="chip chip-amber text-[0.65rem]">plan changed</span>
          )}
          {pdfUrl && (
            <>
              <button
                type="button"
                className="btn"
                onClick={() => window.open(pdfUrl, "_blank", "noopener")}
              >
                Open in new tab
              </button>
              <button
                type="button"
                className="btn"
                onClick={() =>
                  apiDownload(`/jobs/${id}/resume.pdf?variant=${variant}`, filename)
                }
              >
                Download
              </button>
            </>
          )}
          {owner && status.has_plan && (
            <button
              type="button"
              className={pdfUrl ? "btn" : "btn btn-primary"}
              disabled={busy}
              onClick={render}
            >
              {busy
                ? "Generating…"
                : pdfUrl
                  ? vs.stale
                    ? "Regenerate"
                    : "Re-generate"
                  : `Generate ${variant === "onepage" ? "1-page" : "2-page"}`}
            </button>
          )}
        </div>
      </div>

      {error && <p className="mb-2 text-sm text-red">{error}</p>}

      {pdfUrl ? (
        <object
          data={pdfUrl}
          type="application/pdf"
          className="h-[85vh] w-full rounded-lg border border-[var(--line)] bg-white"
          aria-label={`Tailored resume, ${variant === "onepage" ? "one" : "two"} page`}
        >
          <p className="p-4 text-sm text-dim">
            Your browser can’t embed PDFs.{" "}
            <button type="button" className="underline" onClick={() => window.open(pdfUrl, "_blank")}>
              Open it in a new tab
            </button>
            .
          </p>
        </object>
      ) : status.has_plan ? (
        <p className="text-sm text-faint">
          {owner
            ? `Generate the ${variant === "onepage" ? "1-page" : "2-page"} resume to preview it here.`
            : "No tailored resume has been generated yet."}
        </p>
      ) : (
        <p className="text-sm text-faint">Tailor this job first.</p>
      )}
    </section>
  );
}

