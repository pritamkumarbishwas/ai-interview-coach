"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, toApiError } from "@/lib/api";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
}

/**
 * Runs `loader` on mount, whenever `deps` change and on every `reload()`.
 * Responses from superseded runs are discarded, so a slow first request can
 * never overwrite a newer one.
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: React.DependencyList = [],
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const loaderRef = useRef(loader);
  const runIdRef = useRef(0);

  useEffect(() => {
    loaderRef.current = loader;
  }, [loader]);

  const start = useCallback(() => {
    const runId = ++runIdRef.current;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    loaderRef
      .current()
      .then((data) => {
        if (runId === runIdRef.current) {
          setState({ data, loading: false, error: null });
        }
      })
      .catch((error: unknown) => {
        if (runId === runIdRef.current) {
          setState({ data: null, loading: false, error: toApiError(error) });
        }
      });
  }, []);

  // `deps` is caller-provided; its length is stable for a given call site.
  useEffect(() => {
    start();
    return () => {
      // Invalidate in-flight work when deps change or the component unmounts.
      runIdRef.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, start]);

  const reload = useCallback(() => {
    start();
  }, [start]);

  return { ...state, reload };
}
