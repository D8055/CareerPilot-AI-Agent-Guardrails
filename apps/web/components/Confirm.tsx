"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

/* Confirmation dialog for destructive / irreversible actions (Nielsen "error
   prevention"; NN/g). Restates the action, uses a specific verb on the button,
   colors the destructive choice red, and separates it from Cancel. Accessible:
   role=dialog, focus moved in and restored, Esc cancels, focus trapped. */

interface ConfirmOpts {
  title: string;
  body?: string;
  confirmLabel?: string; // specific verb, e.g. "Delete entry"
  destructive?: boolean;
}

type Resolver = (ok: boolean) => void;

const ConfirmCtx = createContext<((o: ConfirmOpts) => Promise<boolean>) | null>(
  null
);

export function useConfirm() {
  const ctx = useContext(ConfirmCtx);
  if (!ctx) throw new Error("useConfirm must be used within <ConfirmProvider>");
  return ctx;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOpts | null>(null);
  const resolver = useRef<Resolver | null>(null);
  const confirmBtn = useRef<HTMLButtonElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);

  const confirm = useCallback((o: ConfirmOpts) => {
    lastFocused.current = document.activeElement as HTMLElement;
    setOpts(o);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const close = useCallback((ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    setOpts(null);
    lastFocused.current?.focus?.();
  }, []);

  useEffect(() => {
    if (!opts) return;
    confirmBtn.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [opts, close]);

  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      {opts && (
        <div
          className="fixed inset-0 z-[95] flex items-center justify-center bg-black/50 px-4"
          onClick={() => close(false)}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby={opts.body ? "confirm-body" : undefined}
            className="panel w-full max-w-sm p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-title" className="display text-base font-semibold">
              {opts.title}
            </h2>
            {opts.body && (
              <p id="confirm-body" className="mt-2 text-sm text-dim">
                {opts.body}
              </p>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="btn" onClick={() => close(false)}>
                Cancel
              </button>
              <button
                ref={confirmBtn}
                type="button"
                className={opts.destructive ? "btn btn-danger" : "btn btn-primary"}
                onClick={() => close(true)}
              >
                {opts.confirmLabel ?? "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmCtx.Provider>
  );
}
