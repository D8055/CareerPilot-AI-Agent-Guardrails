"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, WS_URL } from "./api";

/** Fetch once on mount, expose refetch. Latest fn is tracked via a ref. */
export function useApi<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);

  useEffect(() => {
    fnRef.current = fn;
  });

  const refetch = useCallback(async () => {
    try {
      const result = await fnRef.current();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { data, error, loading, refetch };
}

/**
 * Live refresh: subscribe to the API WebSocket and call onEvent on every
 * broadcast; poll every 15s as a backstop (and as the fallback when the
 * socket cannot connect). Returns whether the socket is currently open.
 */
export function useLive(onEvent: () => void) {
  const [wsOpen, setWsOpen] = useState(false);
  const cbRef = useRef(onEvent);

  useEffect(() => {
    cbRef.current = onEvent;
  });

  useEffect(() => {
    let ws: WebSocket | null = null;
    let disposed = false;
    let debounce: ReturnType<typeof setTimeout> | null = null;

    const poll = setInterval(() => cbRef.current(), 15000);

    try {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        if (!disposed) setWsOpen(true);
      };
      ws.onmessage = () => {
        if (debounce) clearTimeout(debounce);
        debounce = setTimeout(() => cbRef.current(), 400);
      };
      ws.onclose = () => {
        if (!disposed) setWsOpen(false);
      };
      ws.onerror = () => {
        if (!disposed) setWsOpen(false);
      };
    } catch {
      // constructor failed; wsOpen is already false and polling covers us
    }

    return () => {
      disposed = true;
      clearInterval(poll);
      if (debounce) clearTimeout(debounce);
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }, []);

  return wsOpen;
}
