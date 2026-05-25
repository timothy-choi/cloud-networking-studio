import { ApiError, formatApiError, parseStructuredError } from '../../api/client';

function redactSecrets(value: unknown): unknown {
  if (value == null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map(redactSecrets);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    const lk = k.toLowerCase();
    if (lk.includes('token') || lk.includes('secret') || lk.includes('password') || lk === 'authorization') {
      out[k] = '[redacted]';
    } else if (typeof v === 'object') {
      out[k] = redactSecrets(v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

export function ApiErrorDisplay({
  error,
  className = '',
}: {
  error: unknown;
  className?: string;
}) {
  const friendly = formatApiError(error);
  const structured = error instanceof ApiError ? parseStructuredError(error.detail) : null;
  const requestId = structured?.request_id ?? (error instanceof ApiError ? error.requestId : null);
  const code = structured?.code ?? null;
  const technical =
    error instanceof ApiError
      ? {
          endpoint: error.url,
          status: error.status,
          statusText: error.statusText,
          body: redactSecrets(error.detail),
        }
      : error instanceof Error
        ? { message: error.message }
        : error;

  return (
    <div
      className={`rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100 ${className}`}
      role="alert"
    >
      <div className="whitespace-pre-wrap">{friendly}</div>
      {error instanceof ApiError ? (
        <div className="mt-2 space-y-0.5 font-mono text-[11px] opacity-90">
          {error.url ? <div>endpoint: {error.url}</div> : null}
          <div>
            http: {error.status} {error.statusText}
          </div>
        </div>
      ) : null}
      {code ? <div className="mt-1 font-mono text-[11px] opacity-80">Code: {code}</div> : null}
      {requestId ? (
        <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[11px]">
          <span>request_id: {requestId}</span>
          <button
            type="button"
            className="rounded border border-red-300 px-1.5 py-0.5 text-[10px] dark:border-red-700"
            onClick={() => void navigator.clipboard?.writeText(requestId)}
          >
            Copy
          </button>
        </div>
      ) : null}
      {error instanceof ApiError ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] font-medium">Response body</summary>
          <pre className="mt-2 max-h-40 overflow-auto rounded bg-white/60 p-2 font-mono text-[10px] dark:bg-black/30">
            {JSON.stringify(technical, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
