"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";
import { clearSession, getRole, getToken } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

const emptySubscribe = () => () => {};
const nullSnapshot = () => null;

const NAV = [
  { href: "/", label: "Board" },
  { href: "/career", label: "Career" },
  { href: "/evals", label: "Evals" },
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
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 sm:px-6">
      <header className="sticky top-0 z-20 -mx-4 border-b border-line bg-[color-mix(in_srgb,var(--bg)_88%,transparent)] px-4 pt-3 pb-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-4">
          <Link href="/" className="shrink-0">
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-4 overflow-x-auto sm:gap-5">
            {NAV.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/" || pathname.startsWith("/jobs")
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
      <main className="flex-1 py-6">{children}</main>
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
