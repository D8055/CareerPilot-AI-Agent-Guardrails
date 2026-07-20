"use client";

import { useCallback, useState } from "react";
import { api, isOwner } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Blocker, BlockerStatus } from "@/lib/types";
import { EmptyState, ErrorNote, Eyebrow, Loading } from "@/components/ui";

const MCP_COMMAND = "claude mcp add careerpilot -- python apps/api/mcp_server.py";

const BLOCKER_STATUSES: BlockerStatus[] = [
  "waiting_on_dhiren",
  "resolved",
  "deferred",
];

export default function SettingsPage() {
  const owner = isOwner();
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="display text-2xl font-bold">Settings</h1>
      </header>
      <ConnectClaude />
      <Blockers owner={owner} />
      {owner && <Share />}
    </div>
  );
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button type="button" className="btn shrink-0" onClick={copy}>
      {copied ? "Copied ✓" : label}
    </button>
  );
}

function ConnectClaude() {
  return (
    <section className="panel p-5">
      <h2 className="display text-base font-semibold">Connect Claude</h2>
      <p className="mt-1 mb-3 text-sm text-dim">
        Register CareerPilot as an MCP server. Any MCP client — Claude Code,
        Claude Desktop, or anything else that speaks MCP — can drive the whole
        product through it.
      </p>
      <div className="flex items-center gap-2">
        <pre className="readout flex-1 overflow-x-auto rounded-lg bg-panel2 px-3 py-2.5 text-[0.75rem]">
          {MCP_COMMAND}
        </pre>
        <CopyButton text={MCP_COMMAND} />
      </div>
    </section>
  );
}

function Blockers({ owner }: { owner: boolean }) {
  const blockers = useApi(useCallback(() => api<Blocker[]>("/status/blockers"), []));
  const [error, setError] = useState<string | null>(null);

  async function setStatus(code: string, status: BlockerStatus) {
    setError(null);
    try {
      await api(`/status/blockers/${code}`, { method: "PATCH", body: { status } });
      await blockers.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the blocker.");
    }
  }

  const list = blockers.data ?? [];
  const order: Record<BlockerStatus, number> = {
    waiting_on_dhiren: 0,
    deferred: 1,
    resolved: 2,
  };
  const sorted = [...list].sort(
    (a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3)
  );
  const waiting = list.filter((b) => b.status === "waiting_on_dhiren").length;

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="display text-base font-semibold">Waiting on Dhiren</h2>
        <span className={waiting > 0 ? "chip chip-amber" : "chip chip-green"}>
          {waiting > 0 ? `${waiting} need${waiting === 1 ? "s" : ""} you` : "all clear"}
        </span>
      </div>
      <p className="mt-1 mb-3 text-sm text-dim">
        The launch checklist only you can move. Resolve items here to unblock
        each phase.
      </p>
      {error && (
        <div className="mb-3">
          <ErrorNote message={error} />
        </div>
      )}
      {blockers.loading ? (
        <Loading label="Loading blockers" />
      ) : blockers.error ? (
        <ErrorNote message={blockers.error} />
      ) : sorted.length === 0 ? (
        <EmptyState>No blockers recorded.</EmptyState>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--line)]">
          {sorted.map((b) => {
            const isWaiting = b.status === "waiting_on_dhiren";
            const isResolved = b.status === "resolved";
            return (
              <li
                key={b.code}
                className={`flex flex-wrap items-start gap-3 py-3 ${
                  b.status === "deferred" ? "opacity-55" : ""
                }`}
              >
                {isWaiting && (
                  <span
                    className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-amber"
                    aria-label="Waiting on Dhiren"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`text-sm font-semibold ${
                        isResolved ? "text-faint line-through" : ""
                      }`}
                    >
                      {b.title}
                    </span>
                    <span className="chip chip-cyan">{b.phase}</span>
                    <span className="readout text-[0.65rem] text-faint">{b.code}</span>
                  </div>
                  <p
                    className={`mt-0.5 text-xs ${
                      isResolved ? "text-faint line-through" : "text-dim"
                    }`}
                  >
                    {b.detail}
                  </p>
                </div>
                {owner ? (
                  <select
                    className="select w-44 shrink-0 text-xs"
                    value={b.status}
                    onChange={(e) => setStatus(b.code, e.target.value as BlockerStatus)}
                    aria-label={`Status for ${b.title}`}
                  >
                    {BLOCKER_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className={isWaiting ? "chip chip-amber" : "chip"}>
                    {b.status.replaceAll("_", " ")}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Share() {
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function share() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ viewer_token: string }>("/auth/share", {
        method: "POST",
      });
      setToken(res.viewer_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create a viewer token.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-5">
      <h2 className="display text-base font-semibold">Share</h2>
      <p className="mt-1 mb-3 text-sm text-dim">
        Create a read-only viewer token. Viewers see everything but can change
        nothing.
      </p>
      <button type="button" className="btn btn-primary" onClick={share} disabled={busy}>
        {busy ? "Creating…" : "Create viewer token"}
      </button>
      {error && <p className="mt-2 text-sm text-red">{error}</p>}
      {token && (
        <div className="mt-3">
          <Eyebrow>viewer token</Eyebrow>
          <div className="mt-1.5 flex items-center gap-2">
            <pre className="readout flex-1 overflow-x-auto rounded-lg bg-panel2 px-3 py-2.5 text-[0.7rem]">
              {token}
            </pre>
            <CopyButton text={token} />
          </div>
        </div>
      )}
    </section>
  );
}
