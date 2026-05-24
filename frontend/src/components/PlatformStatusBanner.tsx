import { useEffect, useState } from 'react';

import { apiFetch, formatApiError } from '../api/client';

type RuntimeStatusPayload = {
  backend_status?: string;
  status?: string;
  runtime_executor?: string;
  runtime_provider?: string;
  runner_reachable?: boolean;
  docker_reachable?: boolean;
  kubernetes_reachable?: boolean;
  current_context?: string;
  kubeconfig_source?: string;
  kubernetes_init_error?: string;
  message?: string;
  last_runtime_error?: string | null;
  environment?: string;
};

function fmtBool(v: boolean | undefined): string {
  if (v === true) return 'yes';
  if (v === false) return 'no';
  return '—';
}

export function PlatformStatusBanner() {
  const [data, setData] = useState<RuntimeStatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const json = await apiFetch<RuntimeStatusPayload>('/runtime/status');
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(formatApiError(e));
          setData(null);
        }
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="max-w-xl rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100">
        Platform status unavailable ({error})
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] text-cns-muted dark:border-zinc-700 dark:bg-zinc-900/60">
        Loading platform status…
      </div>
    );
  }

  const providerHint =
    data.runtime_provider === 'kubernetes'
      ? 'Advanced Kubernetes runtime — ensure RUNTIME_PROVIDER=kubernetes on the Go runner and a reachable kubeconfig.'
      : 'Docker is the stable default runtime provider for production.';

  const line = [
    `API ${data.backend_status ?? '—'}`,
    `exec ${data.runtime_executor ?? '—'}`,
    `provider ${data.runtime_provider ?? '—'}`,
    `runner ${fmtBool(data.runner_reachable)}`,
    `docker ${fmtBool(data.docker_reachable)}`,
    `k8s ${fmtBool(data.kubernetes_reachable)}`,
    data.current_context ? `ctx ${data.current_context}` : null,
    data.environment ? `env ${data.environment}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  const err = (data.last_runtime_error || data.message || '').trim();

  return (
    <div className="max-w-2xl rounded-md border border-zinc-200 bg-white/90 px-2 py-1 text-[11px] text-zinc-800 shadow-sm dark:border-zinc-700 dark:bg-zinc-900/80 dark:text-zinc-100">
      <div className="font-semibold text-zinc-600 dark:text-zinc-300">Platform</div>
      <div className="font-mono text-[10px] leading-snug text-zinc-700 dark:text-zinc-200">{line}</div>
      <div className="mt-0.5 text-[10px] text-cns-muted">{providerHint}</div>
      {err ? (
        <div className="mt-0.5 truncate text-amber-800 dark:text-amber-200" title={err}>
          Last note: {err}
        </div>
      ) : null}
    </div>
  );
}
