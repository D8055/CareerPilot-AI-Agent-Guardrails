"use client";

import { useCallback, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { CareerItem, RagHit } from "@/lib/types";
import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Loading,
  TierBadge,
} from "@/components/ui";

export default function CareerPage() {
  const career = useApi(useCallback(() => api<CareerItem[]>("/career"), []));

  const sections = new Map<string, CareerItem[]>();
  for (const item of career.data ?? []) {
    const key = item.section || "other";
    const list = sections.get(key) ?? [];
    list.push(item);
    sections.set(key, list);
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
                        {item.ref} · {item.kind}
                      </div>
                    </div>
                    <TierBadge tier={item.tier} />
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
                    {h.ref} · {h.section} · {h.kind}
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
