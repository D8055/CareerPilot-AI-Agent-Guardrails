"use client";

import { useCallback, useRef, useState, type FormEvent } from "react";
import { api, apiDownload, apiUpload, isOwner } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { CareerItem, RagHit, ResumeMeta } from "@/lib/types";
import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Loading,
  TierBadge,
} from "@/components/ui";

export default function CareerPage() {
  const career = useApi(useCallback(() => api<CareerItem[]>("/career"), []));
  const owner = isOwner();

  const sections = new Map<string, CareerItem[]>();
  for (const item of career.data ?? []) {
    const key = item.section || "other";
    const list = sections.get(key) ?? [];
    list.push(item);
    sections.set(key, list);
  }

  async function remove(id: number | string) {
    await api(`/career/items/${id}`, { method: "DELETE" });
    career.refetch();
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="display text-2xl font-bold">Career record</h1>
        <p className="mt-1 text-sm text-dim">
          The only source resumes are built from. Tier 1 = confirmed with
          Dhiren; nothing below that reaches a resume.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ResumePanel owner={owner} />
        {owner && <AddItemPanel onAdded={career.refetch} />}
      </div>

      <RagSearch />

      {career.loading ? (
        <Loading label="Reading the record" />
      ) : career.error ? (
        <ErrorNote message={career.error} />
      ) : sections.size === 0 ? (
        <EmptyState>The career record is empty.</EmptyState>
      ) : (
        <div className="flex flex-col gap-6">
          {[...sections.entries()].map(([section, items]) => (
            <section key={section}>
              <div className="mb-2 flex items-baseline gap-2 px-1">
                <h2 className="display text-base font-semibold capitalize">
                  {section}
                </h2>
                <span className="readout text-xs text-faint">{items.length}</span>
              </div>
              <div className="panel divide-y divide-[var(--line)]">
                {items.map((item) => (
                  <div key={item.id} className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm leading-relaxed">{item.text}</p>
                      <div className="readout mt-1 text-[0.65rem] text-faint">
                        {item.ref || "owner-added"} · {item.kind}
                        {item.source === "owner" && " · added by you"}
                      </div>
                    </div>
                    <TierBadge tier={item.tier} />
                    {owner && item.source === "owner" && (
                      <button
                        type="button"
                        className="btn btn-quiet px-2 py-1 text-xs"
                        title="Remove this item"
                        onClick={() => remove(item.id)}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function ResumePanel({ owner }: { owner: boolean }) {
  const meta = useApi(useCallback(() => api<ResumeMeta>("/resume"), []));
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      await apiUpload("/resume", file);
      meta.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  const m = meta.data;
  return (
    <section className="panel p-5">
      <Eyebrow>resume on file</Eyebrow>
      {meta.loading ? (
        <Loading label="Checking" />
      ) : m?.uploaded ? (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{m.filename}</p>
            <p className="readout mt-0.5 text-[0.65rem] text-faint">
              {((m.size ?? 0) / 1024).toFixed(0)} KB · uploaded{" "}
              {m.ts ? new Date(m.ts + "Z").toLocaleString() : ""}
            </p>
          </div>
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              className="btn"
              onClick={() => apiDownload("/resume/download", m.filename ?? "resume")}
            >
              Download
            </button>
            {owner && (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
              >
                {busy ? "Uploading…" : "Replace"}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-2">
          <p className="text-sm text-dim">
            No resume uploaded yet.
            {owner ? " Upload your master resume (docx or pdf)." : ""}
          </p>
          {owner && (
            <button
              type="button"
              className="btn btn-primary mt-3"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              {busy ? "Uploading…" : "Upload resume"}
            </button>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
      <input
        ref={fileRef}
        type="file"
        accept=".docx,.pdf,.doc"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = "";
        }}
      />
    </section>
  );
}

function AddItemPanel({ onAdded }: { onAdded: () => void }) {
  const [text, setText] = useState("");
  const [section, setSection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await api("/career/items", {
        method: "POST",
        body: { text, section },
      });
      setText("");
      setDone(true);
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add it.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-5">
      <Eyebrow>add to the record</Eyebrow>
      <p className="mt-1 mb-3 text-xs text-dim">
        Plain text, one fact at a time. It joins the record and the evidence
        index immediately — only add things that are true and yours.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <textarea
          className="textarea min-h-20"
          placeholder="e.g. Built a Slack bot in Python that posts a weekly digest to my team channel"
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="Section (optional, e.g. Projects)"
            value={section}
            onChange={(e) => setSection(e.target.value)}
          />
          <button type="submit" className="btn btn-primary shrink-0" disabled={busy}>
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      </form>
      {done && <p className="mt-2 text-sm text-green">Added to the record.</p>}
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
    </section>
  );
}

function RagSearch() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<RagHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<RagHit[]>("/rag/query", {
        method: "POST",
        body: { text: query, k: 5 },
      });
      setHits(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-5">
      <Eyebrow>evidence search</Eyebrow>
      <p className="mt-1 mb-3 text-xs text-dim">
        Ask the record a question — top 5 pieces of evidence, scored.
      </p>
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="input"
          placeholder="e.g. distributed systems experience"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          required
        />
        <button type="submit" className="btn btn-primary shrink-0" disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
      {hits !== null && (
        <div className="mt-3 flex flex-col gap-2">
          {hits.length === 0 ? (
            <p className="text-sm text-faint">No evidence found for that query.</p>
          ) : (
            hits.map((h, i) => (
              <div key={`${h.ref}-${i}`} className="rounded-lg bg-panel2 px-3 py-2.5">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="readout text-[0.65rem] text-faint">
                    {h.ref || "owner-added"} · {h.section} · {h.kind}
                  </span>
                  <span className="readout text-xs font-semibold text-cyan">
                    {typeof h.score === "number" ? h.score.toFixed(3) : h.score}
                  </span>
                </div>
                <p className="mt-1 text-sm leading-relaxed">{h.text}</p>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}
