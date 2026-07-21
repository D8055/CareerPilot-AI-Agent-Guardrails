"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

/* Toast feedback for completed actions (Nielsen "visibility of system status";
   WCAG 4.1.3 status messages). Top-right, auto-dismiss ~4s, dismissible.
   Success and error carry an icon so color is never the only signal (1.4.1). */

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  message: string;
}

interface ToastApi {
  toast: (message: string, tone?: Tone) => void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

let nextId = 1;

const ICON: Record<Tone, string> = { success: "✓", error: "✕", info: "•" };
const TONE_CLASS: Record<Tone, string> = {
  success: "chip-green",
  error: "chip-red",
  info: "chip-cyan",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const remove = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const push = useCallback((message: string, tone: Tone = "info") => {
    const id = nextId++;
    setToasts((t) => [...t, { id, tone, message }]);
  }, []);

  const api: ToastApi = {
    toast: push,
    success: (m) => push(m, "success"),
    error: (m) => push(m, "error"),
  };

  return (
    <ToastCtx.Provider value={api}>
      {children}
      {/* polite live region: announced to screen readers without stealing focus */}
      <div
        className="pointer-events-none fixed top-3 right-3 z-[90] flex w-[min(24rem,calc(100vw-1.5rem))] flex-col gap-2"
        role="status"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((t) => (
          <ToastRow key={t.id} toast={t} onDone={() => remove(t.id)} />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastRow({ toast, onDone }: { toast: Toast; onDone: () => void }) {
  useEffect(() => {
    const ms = toast.tone === "error" ? 6000 : 4000; // errors linger longer
    const timer = setTimeout(onDone, ms);
    return () => clearTimeout(timer);
  }, [toast.tone, onDone]);

  return (
    <div className="toast panel pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5">
      <span className={`chip ${TONE_CLASS[toast.tone]} mt-0.5 shrink-0`} aria-hidden>
        {ICON[toast.tone]}
      </span>
      <p className="flex-1 text-sm leading-snug">{toast.message}</p>
      <button
        type="button"
        className="tap btn-quiet -mr-1.5 -mt-1 rounded px-1.5 text-faint"
        onClick={onDone}
        aria-label="Dismiss notification"
      >
        ✕
      </button>
    </div>
  );
}
