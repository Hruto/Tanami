import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (update: (current: T | null) => T | null) => void;
}

/** Load once per ``key`` change; stale responses from an older key are dropped. */
export function useLoad<T>(load: () => Promise<T>, key: string): Loaded<T> {
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loader = useRef(load);
  loader.current = load;

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    loader
      .current()
      .then((value) => current && setDataState(value))
      .catch((reason: unknown) => {
        if (!current) return;
        setError(reason instanceof ApiError ? reason.message : "Data gagal dimuat. Coba muat ulang halaman.");
      })
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [key, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  const setData = useCallback((update: (current: T | null) => T | null) => setDataState(update), []);
  return { data, error, loading, reload, setData };
}

export function messageOf(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Terjadi kesalahan. Coba lagi.";
}
