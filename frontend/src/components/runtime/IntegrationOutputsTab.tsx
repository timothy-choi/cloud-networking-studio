import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import {
  APP_LANGUAGE_OPTIONS,
  fetchDeploymentIntegrationOutputs,
  type AppLanguageKey,
  type DeploymentIntegrationOutputsResponse,
} from '../../api/runtimeIntegration';
import { Spinner } from '../Spinner';
import { CopyButton } from './CopyButton';

type SectionId = 'env' | 'app' | 'cicd' | 'docker' | 'kubernetes';

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: 'env', label: 'Environment variables' },
  { id: 'app', label: 'App code' },
  { id: 'cicd', label: 'CI/CD' },
  { id: 'docker', label: 'Docker Compose' },
  { id: 'kubernetes', label: 'Kubernetes' },
];

function SnippetPanel({
  title,
  language,
  content,
}: {
  title: string;
  language: string;
  content: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-950/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">{title}</h4>
          <span className="text-[10px] uppercase tracking-wide text-cns-muted">{language}</span>
        </div>
        <CopyButton text={content} />
      </div>
      <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
        {content}
      </pre>
    </div>
  );
}

export function IntegrationOutputsTab({ deploymentId }: { deploymentId: string }) {
  const [data, setData] = useState<DeploymentIntegrationOutputsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [section, setSection] = useState<SectionId>('env');
  const [language, setLanguage] = useState<AppLanguageKey>('python');

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setData(await fetchDeploymentIntegrationOutputs(deploymentId));
    } catch (e) {
      setData(null);
      setErr(e instanceof ApiError ? formatApiError(e) : 'Could not load integration outputs.');
    } finally {
      setLoading(false);
    }
  }, [deploymentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const appSnippet = useMemo(() => {
    if (!data) return '';
    return data.outputs[language] ?? '';
  }, [data, language]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner className="h-4 w-4" />
        Loading integration outputs…
      </div>
    );
  }
  if (err) {
    return <p className="text-sm text-red-700 dark:text-red-300">{err}</p>;
  }
  if (!data) return null;

  return (
    <div className="space-y-6">
      <p className="text-sm text-cns-muted">
        Connect this deployment to your own apps, scripts, CI/CD jobs, and local workflows. Copy
        generated snippets below — external URLs are preferred when a service is exposed.
      </p>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-cns-label">Services</h3>
        {data.services.length === 0 ? (
          <p className="mt-1 text-sm text-cns-muted">Deploy and refresh to populate service outputs.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {data.services.map((svc) => (
              <li
                key={svc.name}
                className="rounded border border-zinc-200 bg-zinc-50/80 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950/40"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{svc.name}</span>
                  <span className="font-mono text-[10px] text-cns-muted">{svc.recommended_env_var}</span>
                </div>
                {svc.preferred_url ? (
                  <p className="mt-1 font-mono text-[11px] text-emerald-800 dark:text-emerald-300 break-all">
                    {svc.preferred_url}
                  </p>
                ) : null}
                {svc.endpoint_scope === 'internal_only' && svc.url_note ? (
                  <p className="mt-1 text-[11px] text-amber-800 dark:text-amber-200">{svc.url_note}</p>
                ) : null}
                <p className="mt-1 text-[10px] text-cns-muted">
                  {svc.protocol ?? '—'}
                  {svc.port != null ? ` · port ${svc.port}` : ''}
                  {svc.external_url ? ' · exposed' : svc.internal_url ? ' · internal only' : ''}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex flex-wrap gap-1 border-b border-zinc-200 dark:border-zinc-700">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSection(s.id)}
            className={
              section === s.id
                ? 'border-b-2 border-emerald-600 px-3 py-2 text-xs font-semibold text-emerald-800 dark:border-emerald-400 dark:text-emerald-200'
                : 'border-b-2 border-transparent px-3 py-2 text-xs font-medium text-cns-muted hover:text-zinc-900 dark:hover:text-zinc-100'
            }
          >
            {s.label}
          </button>
        ))}
      </div>

      {section === 'env' ? (
        <SnippetPanel title="Environment variables" language="env" content={data.outputs.env} />
      ) : null}

      {section === 'app' ? (
        <div className="space-y-3">
          <label className="block text-[11px] text-cns-field-label">
            Language
            <select
              className="mt-0.5 rounded-md border border-zinc-600 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100"
              value={language}
              onChange={(e) => setLanguage(e.target.value as AppLanguageKey)}
            >
              {APP_LANGUAGE_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <SnippetPanel
            title={`${APP_LANGUAGE_OPTIONS.find((o) => o.id === language)?.label ?? language} example`}
            language={language}
            content={appSnippet}
          />
          <SnippetPanel title="bash exports" language="bash" content={data.outputs.bash} />
        </div>
      ) : null}

      {section === 'cicd' ? (
        <SnippetPanel title="GitHub Actions" language="yaml" content={data.outputs.github_actions} />
      ) : null}

      {section === 'docker' ? (
        <SnippetPanel title="Docker Compose env" language="yaml" content={data.outputs.docker_compose_env} />
      ) : null}

      {section === 'kubernetes' ? (
        <SnippetPanel
          title="Kubernetes ConfigMap"
          language="yaml"
          content={data.outputs.kubernetes_configmap}
        />
      ) : null}
    </div>
  );
}
