"use client";

import { useEffect } from "react";

/** Per-route document title (WCAG 2.4.2). Pages are client components, so
 * they can't export Next metadata — this sets it on mount instead. */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    const prev = document.title;
    document.title = title ? `${title} · CareerPilot` : "CareerPilot";
    return () => {
      document.title = prev;
    };
  }, [title]);
}
