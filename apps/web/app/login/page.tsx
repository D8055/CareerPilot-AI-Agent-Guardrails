"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, setSession } from "@/lib/api";
import { Wordmark } from "@/components/AppShell";
import { ThemeToggle } from "@/components/ThemeToggle";

interface LoginResponse {
  access_token: string;
  role: string;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [viewerToken, setViewerToken] = useState("");
  const [showViewer, setShowViewer] = useState(false);

  // share links land here as /login?token=<viewer JWT>
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("token");
    if (t) {
      setSession(t, "viewer");
      router.replace("/");
    }
  }, [router]);

  function redeemViewerToken(e: FormEvent) {
    e.preventDefault();
    if (!viewerToken.trim()) return;
    setSession(viewerToken.trim(), "viewer");
    router.replace("/");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
        auth: false,
      });
      setSession(res.access_token, res.role);
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Email or password did not match."
          : err instanceof ApiError
            ? err.message
            : "Sign-in failed."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col px-4">
      <div className="flex justify-end pt-3">
        <ThemeToggle />
      </div>
      <div className="flex flex-1 items-center justify-center pb-24">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex flex-col items-start gap-1.5">
            <Wordmark />
            <p className="eyebrow">flight deck for the job search</p>
          </div>
          <form onSubmit={submit} className="panel flex flex-col gap-4 p-6">
            <label className="flex flex-col gap-1.5">
              <span className="eyebrow">Email</span>
              <input
                className="input"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="eyebrow">Password</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && <p className="text-sm text-red">{error}</p>}
            <button type="submit" className="btn btn-primary justify-center" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          {showViewer ? (
            <form onSubmit={redeemViewerToken} className="mt-4 flex gap-2">
              <input
                className="input flex-1"
                placeholder="Paste viewer token"
                value={viewerToken}
                onChange={(e) => setViewerToken(e.target.value)}
              />
              <button type="submit" className="btn">
                View
              </button>
            </form>
          ) : (
            <button
              type="button"
              className="mt-4 text-xs text-faint underline-offset-2 hover:underline"
              onClick={() => setShowViewer(true)}
            >
              Have a viewer token from the owner? Use it here.
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
