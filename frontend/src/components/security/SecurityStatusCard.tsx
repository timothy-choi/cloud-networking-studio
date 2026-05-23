import { useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import { getSecurityStatus } from '../../api/securityStatus';
import type { SecurityStatusResponse } from '../../types/securityStatus';

function StatusRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-xs">
      <span className="text-cns-muted">{label}</span>
      <span className={ok ? 'font-medium text-emerald-700 dark:text-emerald-400' : 'font-medium text-amber-800 dark:text-amber-300'}>
        {ok ? 'OK' : detail ?? 'Review'}
      </span>
    </div>
  );
}

export function SecurityStatusCard() {
  const [data, setData] = useState<SecurityStatusResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void getSecurityStatus()
      .then(setData)
      .catch((e) => setErr(formatApiError(e)));
  }, []);

  if (err) return <p className="text-sm text-red-700 dark:text-red-300">{err}</p>;
  if (!data) return <p className="text-sm text-cns-muted">Loading security status…</p>;

  return (
    <div className="space-y-3">
      <dl className="space-y-2 rounded-lg border border-zinc-200 px-3 py-3 dark:border-zinc-700">
        <StatusRow label="Auth secret configured" ok={data.auth_secret_configured} />
        <StatusRow label="Auth secret strong" ok={data.auth_secret_strong} detail="Set AUTH_SECRET_KEY" />
        <StatusRow label="CORS strict" ok={data.cors_strict} detail="Avoid wildcard origins" />
        <StatusRow label="API token scopes" ok={data.api_token_scopes_enabled} />
        <StatusRow label="Audit logging" ok={data.audit_logging_enabled} />
        <StatusRow label="Runtime provider access" ok={data.runtime_provider_access_configured} />
        <StatusRow label="Login required" ok={data.auth_require_login} detail="Optional in dev" />
      </dl>
      <p className="text-[11px] text-cns-muted">
        Environment: <span className="font-mono">{data.environment}</span>
      </p>
      {data.warnings.length > 0 ? (
        <ul className="space-y-1 text-xs text-amber-900 dark:text-amber-200">
          {data.warnings.map((w) => (
            <li key={w}>• {w}</li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-cns-muted">No security warnings for this environment.</p>
      )}
    </div>
  );
}
