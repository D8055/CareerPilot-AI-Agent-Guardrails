"use client";

import type { ReactNode } from "react";

/* ---------- tiny formatting helpers ---------- */

/** API timestamps are naive UTC; give them a Z so Date doesn't read local. */
function parseTs(ts: string): Date {
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(ts);
  return new Date(hasTz || !ts.includes("T") ? ts : ts + "Z");
}

export function fmtWhen(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = parseTs(ts);
  if (isNaN(d.getTime())) return ts;
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 14) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function fmtDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = parseTs(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ---------- primitives ---------- */

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="panel flex items-start gap-2.5 border-[color-mix(in_srgb,var(--red)_45%,transparent)] px-4 py-3 text-sm text-red"
    >
      {/* icon so color is not the only error signal (WCAG 1.4.1) */}
      <span aria-hidden className="mt-0.5 shrink-0 font-bold">
        ⚠
      </span>
      <span>{message}</span>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="readout flex items-center gap-2 px-1 py-6 text-xs text-faint">
      <span className="pulse inline-block h-2 w-2 rounded-full bg-cyan" />
      {label}…
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="px-1 py-6 text-sm text-faint">{children}</div>
  );
}

/* ---------- domain badges ---------- */

const STATUS_TONE: Record<string, string> = {
  new: "chip",
  discovered: "chip",
  enriched: "chip",
  tailored: "chip chip-cyan",
  applied: "chip chip-accent",
  interview: "chip chip-green",
  offer: "chip chip-green",
  rejected: "chip chip-red",
};

export function StatusChip({ status }: { status: string }) {
  return (
    <span className={STATUS_TONE[status] ?? "chip"}>{status}</span>
  );
}

/**
 * Quality-pass badge. Amber (caution) until a runner has verified the plan:
 * the deterministic result is live, the LLM quality pass is queued.
 */
export function QualityBadge({
  value,
  long = false,
}: {
  value: boolean | string | null | undefined;
  long?: boolean;
}) {
  if (value === true || value === "pass" || value === "passed") {
    return <span className="chip chip-green">quality pass ✓</span>;
  }
  if (value === "fail" || value === "failed") {
    return <span className="chip chip-red">quality pass failed</span>;
  }
  return (
    <span className="chip chip-amber">
      {long ? "deterministic result live; quality pass queued" : "quality pass queued"}
    </span>
  );
}

export function TierBadge({ tier }: { tier: string | number }) {
  const t = String(tier);
  const confirmed = t === "1" || t.toLowerCase().includes("confirm") || t === "tier1";
  return (
    <span className={confirmed ? "chip chip-green" : "chip"}>
      tier {t.replace(/^tier\s*/i, "")}
    </span>
  );
}

/* ---------- match gauge (inline SVG arc) ---------- */

export function matchTone(score: number): string {
  if (score >= 80) return "var(--green)";
  if (score >= 60) return "var(--cyan)";
  return "var(--ink-faint)";
}

export function MatchGauge({
  score,
  size = 40,
  source,
}: {
  score: number | null | undefined;
  size?: number;
  source?: "recruiter" | "keyword" | null;
}) {
  const s = typeof score === "number" ? Math.max(0, Math.min(100, score)) : null;
  const r = 15.5;
  const c = 2 * Math.PI * r;
  // gauge sweeps 270° starting at bottom-left, like an airspeed dial
  const sweep = 0.75 * c;
  const filled = s === null ? 0 : (s / 100) * sweep;
  const tone = s === null ? "var(--ink-faint)" : matchTone(s);
  const kind = source === "recruiter" ? "Recruiter match"
    : source === "keyword" ? "Keyword match" : "Match";
  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      title={s === null ? "No match score yet" : `${kind} ${s}%`}
      aria-label={s === null ? "No match score yet" : `${kind} ${s} percent`}
      role="img"
    >
      <svg viewBox="0 0 40 40" width={size} height={size}>
        <g transform="rotate(135 20 20)">
          <circle
            cx="20"
            cy="20"
            r={r}
            fill="none"
            stroke="var(--line)"
            strokeWidth="3.5"
            strokeDasharray={`${sweep} ${c}`}
            strokeLinecap="round"
          />
          <circle
            cx="20"
            cy="20"
            r={r}
            fill="none"
            stroke={tone}
            strokeWidth="3.5"
            strokeDasharray={`${filled} ${c}`}
            strokeLinecap="round"
          />
        </g>
      </svg>
      <div
        className="readout absolute inset-0 flex items-center justify-center font-semibold"
        style={{ fontSize: size * 0.28, color: tone }}
      >
        {s === null ? "–" : s}
      </div>
    </div>
  );
}
