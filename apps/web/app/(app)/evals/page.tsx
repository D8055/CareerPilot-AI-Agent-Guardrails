"use client";

import { useCallback, useState } from "react";
import { api, isOwner } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { EvalRun } from "@/lib/types";
import { EmptyState, ErrorNote, Loading, fmtDate } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

function metric(run: EvalRun, key: string): string {
  const v = run.metrics?.[key];
  if (v === undefined || v === null) return "—";
  if (typeof v === "number" && !Number.isInteger(v)) return v.toFixed(3);
  return String(v);
}

export default function EvalsPage() {
  useDocumentTitle("Evals");
  const { success, error: toastError } = useToast();
  const owner = isOwner();
  const evals = useApi(useCallback(() => api<EvalRun[]>("/evals"), []));
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function runEvals() {
    setBusy(true);
    setRunError(null);
    try {
      await api("/evals/run", { method: "POST" });
      await evals.refetch();
      success("Evals complete");
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Eval run failed.");
      toastError(err instanceof Error ? err.message : "Eval run failed.");
    } finally {
      setBusy(false);
    }
  }

  const rows = [...(evals.data ?? [])].sort((a, b) =>
    String(b.ts).localeCompare(String(a.ts))
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-2xl font-bold">Evals</h1>
          <p className="mt-1 text-sm text-dim">
            Honesty and retrieval checks over the tailoring matrix.
          </p>
        </div>
        {owner && (
          <button type="button" className="btn btn-primary" onClick={runEvals} disabled={busy}>
            {busy ? "Running…" : "Run evals"}
          </button>
        )}
      </header>

      {runError && <ErrorNote message={runError} />}

      {evals.loading ? (
        <Loading label="Loading eval runs" />
      ) : evals.error ? (
        <ErrorNote message={evals.error} />
      ) : rows.length === 0 ? (
        <EmptyState>
          No eval runs yet.{owner ? " Run evals to get a baseline." : ""}
        </EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="eyebrow px-4 py-3 font-medium">matrix key</th>
                <th className="eyebrow px-4 py-3 font-medium">honesty violations</th>
                <th className="eyebrow px-4 py-3 font-medium">recall@5</th>
                <th className="eyebrow px-4 py-3 font-medium">when</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((run) => {
                const violations = metric(run, "honesty_violations");
                return (
                  <tr key={run.id} className="border-b border-line last:border-0">
                    <td className="readout px-4 py-2.5 text-xs">{run.matrix_key}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={
                          violations !== "—" && Number(violations) > 0
                            ? "chip chip-red"
                            : "chip chip-green"
                        }
                      >
                        {violations}
                      </span>
                    </td>
                    <td className="readout px-4 py-2.5 text-cyan">
                      {metric(run, "retrieval_recall_at_5")}
                    </td>
                    <td className="readout px-4 py-2.5 text-xs text-dim">
                      {fmtDate(run.ts)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
