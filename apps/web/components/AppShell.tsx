"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { api, clearSession, getRole, getToken } from "@/lib/api";
import type { Attention } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";

const emptySubscribe = () => () => {};
const nullSnapshot = () => null;

const NAV = [
  { href: "/", label: "New Jobs" },
  { href: "/board", label: "Board" },
  { href: "/career", label: "Career" },
  { href: "/settings", label: "Settings" },
];

export function Wordmark() {
  return (
    <span className="display inline-flex items-baseline gap-1.5 text-[1.05rem] font-bold tracking-tight">
      {/* course-line glyph */}
      <svg width="15" height="15" viewBox="0 0 15 15" aria-hidden className="translate-y-[1px]">
        <path
          d="M1 12 L7 3 L9.5 8 L14 6"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span>
        Career<span className="text-accent">Pilot</span>
      </span>
    </span>
  );
}

/**
 * Slim caution strip under the header — only rendered when something needs a
 * human: open questions, failed passes/fetches, or the runner being offline.
 * Amber is the "needs Dhiren" color everywhere else; same meaning here.
 */
function NeedsYouBar() {
  const [attention, setAttention] = useState<Attention | null>(null);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const data = await api<Attention>("/attention");
        if (!disposed) setAttention(data);
      } catch {
        if (!disposed) setAttention(null); // API trouble is surfaced elsewhere
      }
    };
    void load();
    const poll = setInterval(load, 30000);
    return () => {
      disposed = true;
      clearInterval(poll);
    };
  }, []);

  const c = attention?.counts;
  const needs =
    !!c && (c.open_questions > 0 || c.failed_items > 0 || !c.runner_online);
  if (!needs) return null;

  return (
    <div
      className="readout -mx-4 flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-[color-mix(in_srgb,var(--amber)_35%,transparent)] bg-[color-mix(in_srgb,var(--amber)_9%,transparent)] px-4 py-1.5 text-[0.7rem] text-amber sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8 xl:-mx-12 xl:px-12"
      role="status"
      aria-label="Needs your attention"
    >
      <span className="eyebrow !text-amber">needs you</span>
      {c.open_questions > 0 && (
        <Link href="/" className="underline-offset-2 hover:underline">
          {c.open_questions} question{c.open_questions === 1 ? "" : "s"}
        </Link>
      )}
      {c.failed_items > 0 && (
        <Link href="/" className="underline-offset-2 hover:underline">
          {c.failed_items} failed
        </Link>
      )}
      {!c.runner_online && (
        <Link href="/settings" className="underline-offset-2 hover:underline">
          quality passes paused
        </Link>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // Session token/role live outside React (sessionStorage); read them as an
  // external store so SSR renders nothing and the client hydrates correctly.
  const token = useSyncExternalStore(emptySubscribe, getToken, nullSnapshot);
  const role = useSyncExternalStore(emptySubscribe, getRole, nullSnapshot);

  useEffect(() => {
    if (!token) router.replace("/login");
  }, [token, router]);

  function signOut() {
    clearSession();
    router.replace("/login");
  }

  if (!token) return null;

  return (
    <div className="flex min-h-screen w-full flex-col px-4 sm:px-6 lg:px-8 xl:px-12">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="sticky top-0 z-20 -mx-4 border-b border-line bg-[color-mix(in_srgb,var(--bg)_88%,transparent)] px-4 pt-3 pb-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8 xl:-mx-12 xl:px-12">
        <div className="flex w-full items-center gap-4">
          <Link href="/" className="shrink-0">
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-4 overflow-x-auto sm:gap-5">
            {NAV.map((item) => {
              // "/" is New Jobs (exact match only); the Board owns /board
              // and every /jobs/* detail page.
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : item.href === "/board"
                    ? pathname.startsWith("/board") || pathname.startsWith("/jobs")
                    : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="navlink"
                  data-active={active}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            {role && (
              <span className={role === "owner" ? "chip chip-accent" : "chip"}>
                {role}
              </span>
            )}
            <ThemeToggle />
            <button type="button" onClick={signOut} className="btn btn-quiet hidden sm:inline-flex">
              Sign out
            </button>
          </div>
        </div>
      </header>
      <NeedsYouBar />
      <main id="main" className="flex-1 py-6">{children}</main>
      <footer className="border-t border-line py-4">
        <div className="readout flex items-center justify-between text-[0.65rem] text-faint">
          <span>CAREERPILOT · PERSONAL FLIGHT DECK</span>
          <button type="button" onClick={signOut} className="sm:hidden underline">
            Sign out
          </button>
        </div>
      </footer>
    </div>
  );
}
