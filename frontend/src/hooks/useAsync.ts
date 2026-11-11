import { useCallback, useEffect, useRef, useState } from "react";
import { ApiException } from "../api/client";

export interface AsyncState<T, A extends unknown[]> {
  data: T | null;
  loading: boolean;
  error: string | null;
  run: (...args: A) => Promise<T | null>;
}

/** Run an async function with loading/error state (for form submits). */
export function useAsync<T, A extends unknown[]>(
  fn: (...args: A) => Promise<T>,
): AsyncState<T, A> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async (...args: A) => {
    setLoading(true);
    setError(null);
    try {
      const out = await fnRef.current(...args);
      setData(out);
      return out;
    } catch (err) {
      setError(
        err instanceof ApiException
          ? err.message
          : "Something went wrong. Please retry.",
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, run };
}

/** Fetch on mount (for GET pages) with a reload handle. */
export function useFetch<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fnRef.current());
    } catch (err) {
      setError(
        err instanceof ApiException
          ? err.message
          : "Something went wrong. Please retry.",
      );
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, loading, error, reload };
}
