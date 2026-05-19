import { useCallback, useEffect, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  fetchDeploymentIntegration,
  type DeploymentIntegrationResponse,
} from '../../api/runtimeIntegration';
import { Spinner } from '../Spinner';
import { SnippetBlock } from './SnippetBlock';
import { CopyButton } from './CopyButton';

export function UseDeploymentTab({ deploymentId }: { deploymentId: string }) {
  const [data, setData] = useState<DeploymentIntegrationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setData(await fetchDeploymentIntegration(deploymentId));
    } catch (e) {
      setData(null);
      setErr(e instanceof ApiError ? formatApiError(e) : 'Could not load integration data.');
    } finally {
      setLoading(false);
    }
  }, [deploymentId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" />
        Loading use-deployment guide…
      </div>
    );
  }
  if (err) {
    return <p className="text-sm text-red-700 dark:text-red-300">{err}</p>;
  }
  if (!data) return null;

  const connect = data.connect_your_app as Record<string, unknown> | undefined;

  return (
    <div className="space-y-6">
      <p className="text-sm text-cns-muted">
        Use this deployment from your laptop, applications, CI/CD, or in-cluster workloads. Copy snippets
        below or open the interactive terminal (members/owners) for advanced debugging.
      </p>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Runtime</h3>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2 text-sm">
          <div>
            <dt className="text-cns-label">Provider</dt>
            <dd className="font-medium">{data.runtime_provider}</dd>
          </div>
          <div>
            <dt className="text-cns-label">Namespace / network</dt>
            <dd className="font-mono text-xs break-all">{data.namespace_or_network ?? '—'}</dd>
          </div>
        </dl>
      </section>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Environment variables</h3>
        {Object.keys(data.env_vars).length === 0 ? (
          <p className="mt-1 text-sm text-cns-muted">No env vars generated yet.</p>
        ) : (
          <div className="mt-2 flex flex-wrap items-start gap-2">
            <pre className="flex-1 rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
              {Object.entries(data.env_vars)
                .map(([k, v]) => `${k}=${v}`)
                .join('\n')}
            </pre>
            <CopyButton
              text={Object.entries(data.env_vars)
                .map(([k, v]) => `${k}=${v}`)
                .join('\n')}
            />
          </div>
        )}
      </section>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Internal endpoints</h3>
        {data.internal_endpoints.length === 0 ? (
          <p className="mt-1 text-sm text-cns-muted">Deploy and refresh to populate service URLs.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {data.internal_endpoints.map((ep, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-zinc-200 bg-zinc-50/80 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950/40"
              >
                <span>
                  <span className="font-medium">{String(ep.name ?? '—')}</span>
                  <span className="ml-2 font-mono text-[11px] text-emerald-800 dark:text-emerald-300">
                    {String(ep.internal_url ?? '')}
                  </span>
                </span>
                {ep.internal_url ? <CopyButton text={String(ep.internal_url)} /> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Exposed / public endpoints</h3>
        {data.exposed_endpoints.length === 0 ? (
          <p className="mt-1 text-sm text-cns-muted">
            Use Expose on the Services tab to publish HTTP routes to your machine.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {data.exposed_endpoints.map((ep, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-zinc-200 px-2 py-1.5 text-sm dark:border-zinc-700"
              >
                <span className="font-mono text-[11px]">{String(ep.external_url ?? 'manual')}</span>
                {ep.external_url ? <CopyButton text={String(ep.external_url)} /> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {connect ? (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">
            {String(connect.title ?? 'Connect your app')}
          </h3>
          {Array.isArray(connect.service_urls) && (connect.service_urls as string[]).length > 0 ? (
            <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
              Service URLs: {(connect.service_urls as string[]).join(', ')}
            </p>
          ) : null}
        </section>
      ) : null}

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Generated examples</h3>
        <div className="mt-3 space-y-3">
          {data.snippets.length === 0 ? (
            <p className="text-sm text-cns-muted">No snippets yet — deploy with runtime metadata first.</p>
          ) : (
            data.snippets.map((s) => <SnippetBlock key={s.id} snippet={s} />)
          )}
        </div>
      </section>
    </div>
  );
}
