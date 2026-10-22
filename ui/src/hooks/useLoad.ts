import { useCallback, useEffect, useState } from "react";

/** Load data for a page; `reload` after a change. Keeps the last good value while reloading. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(() => {
    load().then((d) => { setData(d); setError(null); }).catch((e: Error) => setError(e.message));
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(run, [run]);
  return { data, error, reload: run };
}
