"use client";

import { useCallback, useRef, useState, type FormEvent } from "react";
import { api, apiDownload, apiUpload, isOwner } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { AnswerEntry, CareerItem, RagHit, ResumeMeta } from "@/lib/types";
import {
  EmptyState,
  ErrorNote,
  Eyebrow,
  Loading,
  TierBadge,
} from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useConfirm } from "@/components/Confirm";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

export default function CareerPage() {
  useDocumentTitle("Career");
  const { success, error: toastError } = useToast();
  const confirm = useConfirm();
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
    if (
      !(await confirm({
        title: "Remove this item?",
        body: "It leaves your record and the evidence index.",
        confirmLabel: "Remove",
        destructive: true,
      }))
    )
      return;
    try {
      await api(`/career/items/${id}`, { method: "DELETE" });
      career.refetch();
      success("Removed from the record");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Could not remove it.");
    }
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

      <AnswerBankPanel owner={owner} />

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
                  <CareerItemRow
                    key={item.id}
                    item={item}
                    owner={owner}
                    onRemove={() => remove(item.id)}
                    onSaved={career.refetch}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

/** One record row with inline editing: pencil → textarea → Save. Pool bullets
 * write back to the pool YAML server-side; owner items update directly. Kinds
 * the API refuses to edit come back as a 400 whose detail we toast. */
function CareerItemRow({
  item,
  owner,
  onRemove,
  onSaved,
}: {
  item: CareerItem;
  owner: boolean;
  onRemove: () => void;
  onSaved: () => void;
}) {
  const { success, error: toastError } = useToast();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.text);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await api(`/career/items/${item.id}`, {
        method: "PATCH",
        body: { text: draft },
      });
      setEditing(false);
      onSaved();
      success("Saved to the record");
    } catch (err) {
      // 400s carry the server's reason (e.g. this kind isn't editable)
      toastError(err instanceof Error ? err.message : "Could not save the edit.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        {editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              className="textarea min-h-20"
              aria-label="Edit item text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              autoFocus
            />
            <div className="flex gap-2">
              <button
                type="button"
                className="btn btn-primary px-3 py-1 text-xs"
                disabled={busy || draft.trim().length === 0}
                onClick={save}
              >
                {busy ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                className="btn btn-quiet px-3 py-1 text-xs"
                disabled={busy}
                onClick={() => {
                  setDraft(item.text);
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm leading-relaxed">{item.text}</p>
        )}
        <div className="readout mt-1 text-[0.65rem] text-faint">
          {item.ref || "owner-added"} · {item.kind}
          {item.source === "owner" && " · added by you"}
        </div>
      </div>
      <TierBadge tier={item.tier} />
      {owner && !editing && (
        <button
          type="button"
          className="btn btn-quiet px-2 py-1 text-xs"
          aria-label="Edit this item"
          title="Edit this item"
          onClick={() => {
            setDraft(item.text);
            setEditing(true);
          }}
        >
          ✎
        </button>
      )}
      {owner && item.source === "owner" && !editing && (
        <button
          type="button"
          className="btn btn-quiet px-2 py-1 text-xs"
          title="Remove this item"
          onClick={onRemove}
        >
          ✕
        </button>
      )}
    </div>
  );
}

function ResumePanel({ owner }: { owner: boolean }) {
  const { success, error: toastError } = useToast();
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
      success("Resume uploaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      toastError(err instanceof Error ? err.message : "Upload failed.");
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
  const { success, error: toastError } = useToast();
  const [text, setText] = useState("");
  const [section, setSection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/career/items", {
        method: "POST",
        body: { text, section },
      });
      setText("");
      onAdded();
      success("Added to the record");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add it.");
      toastError(err instanceof Error ? err.message : "Could not add it.");
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
          aria-label="New record fact"
          placeholder="e.g. Built a Slack bot in Python that posts a weekly digest to my team channel"
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <div className="flex gap-2">
          <input
            className="input flex-1"
            aria-label="Section"
            placeholder="Section (optional, e.g. Projects)"
            value={section}
            onChange={(e) => setSection(e.target.value)}
          />
          <button type="submit" className="btn btn-primary shrink-0" disabled={busy}>
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      </form>
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
    </section>
  );
}

function AnswerBankPanel({ owner }: { owner: boolean }) {
  const { success, error: toastError } = useToast();
  const confirm = useConfirm();
  const answers = useApi(useCallback(() => api<AnswerEntry[]>("/answers"), []));
  const [form, setForm] = useState({ question: "", pattern: "", answer: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = { answer: form.answer };
      if (form.question.trim()) body.question = form.question.trim();
      if (form.pattern.trim()) body.pattern = form.pattern.trim();
      await api("/answers", { method: "POST", body });
      setForm({ question: "", pattern: "", answer: "" });
      answers.refetch();
      success("Answer saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the answer.");
      toastError(err instanceof Error ? err.message : "Could not add the answer.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number | string) {
    if (
      !(await confirm({
        title: "Delete this answer?",
        confirmLabel: "Delete",
        destructive: true,
      }))
    )
      return;
    try {
      await api(`/answers/${id}`, { method: "DELETE" });
      answers.refetch();
      success("Answer deleted");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete it.");
      toastError(err instanceof Error ? err.message : "Could not delete it.");
    }
  }

  const list = answers.data ?? [];
  const canAdd =
    form.answer.trim().length > 0 &&
    (form.question.trim().length > 0 || form.pattern.trim().length > 0);

  return (
    <section className="panel p-5">
      <Eyebrow>answer bank</Eyebrow>
      <p className="mt-1 mb-3 text-xs text-dim">
        Canonical answers to application form questions. Unmatched questions
        always ask you first — replies are reused automatically.
      </p>

      {answers.loading ? (
        <Loading label="Reading answers" />
      ) : answers.error ? (
        <ErrorNote message={answers.error} />
      ) : list.length === 0 ? (
        <p className="py-2 text-sm text-faint">
          Nothing learned yet. Form questions you answer once are answered
          automatically forever.
        </p>
      ) : (
        <div className="divide-y divide-[var(--line)]">
          {list.map((entry) => (
            <div key={entry.id} className="flex items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {entry.question ?? (
                    <span className="readout">{entry.pattern}</span>
                  )}
                </p>
                <p className="mt-0.5 text-sm text-dim">↳ {entry.answer}</p>
                {entry.question && entry.pattern && (
                  <p className="readout mt-0.5 text-[0.65rem] text-faint">
                    matches /{entry.pattern}/
                  </p>
                )}
              </div>
              <span className={entry.source === "learned" ? "chip chip-cyan" : "chip"}>
                {entry.source}
              </span>
              <span
                className="readout text-xs text-faint"
                title={`Used ${entry.uses} time${entry.uses === 1 ? "" : "s"}`}
              >
                ×{entry.uses}
              </span>
              {owner && (
                <button
                  type="button"
                  className="btn btn-quiet px-2 py-1 text-xs"
                  title="Delete this answer"
                  onClick={() => remove(entry.id)}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {owner && (
        <form onSubmit={add} className="mt-3 flex flex-col gap-2 border-t border-line pt-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input
              className="input"
              aria-label="Question"
              placeholder="Question, e.g. Are you willing to relocate?"
              value={form.question}
              onChange={(e) => setForm({ ...form, question: e.target.value })}
            />
            <input
              className="input"
              aria-label="Match pattern (regex)"
              placeholder="optional regex, e.g. salary|compensation"
              value={form.pattern}
              onChange={(e) => setForm({ ...form, pattern: e.target.value })}
            />
          </div>
          <div className="flex gap-2">
            <input
              className="input flex-1"
              aria-label="Answer"
              placeholder="Answer"
              value={form.answer}
              onChange={(e) => setForm({ ...form, answer: e.target.value })}
              required
            />
            <button
              type="submit"
              className="btn btn-primary shrink-0"
              disabled={busy || !canAdd}
            >
              {busy ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      )}
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
          aria-label="Evidence search query"
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
