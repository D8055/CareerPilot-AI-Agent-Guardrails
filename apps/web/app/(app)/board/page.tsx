"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type DragEvent } from "react";
import { api, apiDownload, isOwner } from "@/lib/api";
import { useApi, useLive } from "@/lib/hooks";
import type { Job } from "@/lib/types";
import { PIPELINE_STATUSES, displayMatch } from "@/lib/types";
import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Loading,
  MatchGauge,
  StatusChip,
  fmtWhen,
} from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

const COLUMNS = [...PIPELINE_STATUSES]; // tailored → … → rejected (muted)

export default function BoardPage() {
  useDocumentTitle("Board");
  const owner = isOwner();
  const { success, error: toastError } = useToast();

  const jobs = useApi(useCallback(() => api<Job[]>("/jobs"), []));
  const refreshAll = useCallback(() => {
    jobs.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.refetch]);
  useLive(refreshAll);

  // Board | Table — persisted per browser; read after mount so SSR matches.
  const [view, setView] = useState<"board" | "table">("board");
  useEffect(() => {
    if (localStorage.getItem("cp_pipeline_view") === "table") setView("table");
  }, []);
  const pickView = useCallback((v: "board" | "table") => {
    setView(v);
    localStorage.setItem("cp_pipeline_view", v);
  }, []);

  // only pipeline jobs live here; the "new" bucket has its own page
  const pipelineJobs = (jobs.data ?? []).filter((j) =>
    (COLUMNS as string[]).includes(j.status)
  );
  const byColumn: Record<string, Job[]> = {};
  for (const job of pipelineJobs) (byColumn[job.status] ??= []).push(job);

  /** Drop handler: PATCH the dragged job into the target column. */
  async function moveJob(id: string, status: string) {
    try {
      await api(`/jobs/${id}/status`, { method: "PATCH", body: { status } });
      refreshAll();
      success(`Moved to ${status}`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Could not move the job.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* ---- pipeline summary strip ---- */}
      <section aria-label="Pipeline summary">
        <div className="panel readout flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-2.5 text-xs">
          {COLUMNS.map((col) => (
            <span key={col} className="flex items-baseline gap-1.5">
              <span className="eyebrow">{col}</span>
              <span className="font-semibold">
                {jobs.data ? (byColumn[col] ?? []).length : "–"}
              </span>
            </span>
          ))}
        </div>
      </section>

      {jobs.error && <ErrorNote message={jobs.error} />}

      <section aria-label="Pipeline board" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="display text-lg font-semibold">Board</h1>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <ViewToggle view={view} onChange={pickView} />
            <ExportCsv />
          </div>
        </div>

        {jobs.loading ? (
          <Loading label="Reading the pipeline" />
        ) : pipelineJobs.length === 0 ? (
          <EmptyState>
            Nothing in the pipeline yet. Apply to a job from New Jobs and it
            lands here in Tailored.
          </EmptyState>
        ) : view === "table" ? (
          <JobsTable jobs={pipelineJobs} />
        ) : (
          <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6">
            {/* columns grow to share the full width; scroll only when cramped */}
            <div className="flex gap-3">
              {COLUMNS.map((col) => (
                <BoardColumn
                  key={col}
                  status={col}
                  jobs={byColumn[col] ?? []}
                  canDrag={owner}
                  onDropJob={(id) => moveJob(id, col)}
                />
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

/* ---- kanban column: native HTML5 drop target ---- */

function BoardColumn({
  status,
  jobs,
  canDrag,
  onDropJob,
}: {
  status: string;
  jobs: Job[];
  canDrag: boolean;
  onDropJob: (id: string) => void;
}) {
  const [over, setOver] = useState(false);
  const muted = status === "rejected";

  function onDragOver(e: DragEvent) {
    e.preventDefault(); // allow drop
    e.dataTransfer.dropEffect = "move";
    setOver(true);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const id = e.dataTransfer.getData("application/x-careerpilot-job");
    if (id) onDropJob(id);
  }

  return (
    <div
      className={`min-w-[12rem] flex-1 ${muted ? "opacity-60" : ""} ${
        over ? "drop-target" : ""
      }`}
      onDragOver={onDragOver}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <div className="mb-2 flex items-baseline justify-between px-1">
        <Eyebrow>{status}</Eyebrow>
        <span className="readout text-xs text-faint">{jobs.length}</span>
      </div>
      <div className="flex flex-col gap-2">
        {jobs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line px-3 py-4 text-center text-xs text-faint">
            empty
          </div>
        ) : (
          jobs.map((job) => <JobCard key={job.id} job={job} canDrag={canDrag} />)
        )}
      </div>
    </div>
  );
}

/* ---- card: company · role · match, nothing else (Huntr-minimal) ---- */

function JobCard({ job, canDrag }: { job: Job; canDrag: boolean }) {
  const m = displayMatch(job);

  function onDragStart(e: DragEvent) {
    e.dataTransfer.setData("application/x-careerpilot-job", String(job.id));
    e.dataTransfer.effectAllowed = "move";
  }

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="panel block cursor-grab p-3 transition-colors hover:border-[var(--accent)] active:cursor-grabbing"
      draggable={canDrag}
      onDragStart={onDragStart}
      title="Drag to move, or change status on the job page"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{job.company}</div>
          <div className="truncate text-xs text-dim">{job.role}</div>
        </div>
        {job.status === "tailoring" ? (
          <span
            className="chip chip-accent shrink-0"
            title="Claude is tailoring this job now"
          >
            <span className="pulse inline-block h-1.5 w-1.5 rounded-full bg-accent" />
            Claude…
          </span>
        ) : (
          <MatchGauge score={m.value} size={38} source={m.source} />
        )}
      </div>
    </Link>
  );
}

/* ---- view toggle & export ---- */

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

/* ---- table view: Company · Role · Status · Match · Added ---- */

type SortKey = "company" | "role" | "status" | "match" | "added_at";

const TABLE_COLS: { key: SortKey; label: string }[] = [
  { key: "company", label: "Company" },
  { key: "role", label: "Role" },
  { key: "status", label: "Status" },
  { key: "match", label: "Match" },
  { key: "added_at", label: "Added" },
];

function compareJobs(a: Job, b: Job, key: SortKey): number {
  if (key === "match")
    return (displayMatch(a).value ?? -1) - (displayMatch(b).value ?? -1);
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
                {/* sort state is aria-only: no arrow glyphs */}
                <button
                  type="button"
                  className="eyebrow cursor-pointer transition-colors hover:!text-[var(--ink)]"
                  onClick={() => clickHeader(col.key)}
                >
                  {col.label}
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
                {(() => {
                  const m = displayMatch(job);
                  return <MatchGauge score={m.value} size={32} source={m.source} />;
                })()}
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
