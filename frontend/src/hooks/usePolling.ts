import { useEffect, useRef } from 'react';

/**
 * Lightweight polling — calls `tick` on mount and every `intervalMs` while `enabled`.
 */
export function usePolling(
  tick: () => void | Promise<void>,
  intervalMs: number,
  enabled: boolean,
): void {
  const saved = useRef(tick);

  useEffect(() => {
    saved.current = tick;
  });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const run = () => {
      if (cancelled) return;
      void Promise.resolve(saved.current());
    };

    run();
    const id = window.setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [intervalMs, enabled]);
}
