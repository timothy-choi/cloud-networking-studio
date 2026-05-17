import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, formatApiError } from '../../api/client';
import { fetchDeploymentRuntime } from '../../api/deploymentRuntime';
import {
  fetchRuntimeDeploymentLogs,
  fetchRuntimeServiceLogs,
  postRuntimeServiceHealth,
  postRuntimeTrafficTest,
} from '../../api/runtimeOperations';
import { exposeDeploymentService, unexposeDeploymentService } from '../../api/serviceExposure';
import { Spinner } from '../Spinner';
import type {
  DeploymentRuntimeDetailResponse,
  RuntimeAccessResourceRow,
  ServiceExposureRow,
} from '../../types/runtime';

const TABS = [
  'overview',
  'nodes',
  'services',
  'endpoints',
  'instructions',
  'op_logs',
  'op_health',
  'op_traffic',
] as const;
type TabId = (typeof TABS)[number];

const TAB_LABEL: Record<TabId, string> = {
  overview: 'Overview',
  nodes: 'Nodes',
  services: 'Services',
  endpoints: 'Endpoints',
  instructions: 'Instructions',
  op_logs: 'Logs',
  op_health: 'Health checks',
  op_traffic: 'Traffic tests',
};

function formatPorts(ports: unknown): string {
  if (ports == null) return '—';
  try {
    return JSON.stringify(ports);
  } catch {
    return String(ports);
  }
}

function InstructionSection({ modeKey, body }: { modeKey: string; body: unknown }) {
  if (body == null || typeof body !== 'object' || Array.isArray(body)) {
    return null;
  }
  const d = body as Record<string, unknown>;
  const title = typeof d.title === 'string' ? d.title : modeKey;
  const commands = Array.isArray(d.commands) ? (d.commands as unknown[]).filter((c) => typeof c === 'string') : [];
  const env = d.env && typeof d.env === 'object' && !Array.isArray(d.env) ? (d.env as Record<string, string>) : null;
  const notes = typeof d.notes === 'string' ? d.notes : null;
  const configMap = d.config_map;
  const endpoints = Array.isArray(d.endpoints) ? d.endpoints : null;
  const items = Array.isArray(d.items) ? d.items : null;

  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-950/40">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-cns-label">{title}</h4>
      {notes ? <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{notes}</p> : null}
      {items && items.length > 0 ? (
        <ul className="mt-2 space-y-2 text-sm text-zinc-800 dark:text-zinc-200">
          {items.map((it, idx) => (
            <li key={idx} className="rounded border border-zinc-200 bg-white/80 px-2 py-1.5 font-mono text-[11px] dark:border-zinc-700 dark:bg-zinc-900/60">
              {typeof it === 'object' && it !== null ? JSON.stringify(it) : String(it)}
            </li>
          ))}
        </ul>
      ) : null}
      {commands.length > 0 ? (
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
          {commands.join('\n')}
        </pre>
      ) : null}
      {env && Object.keys(env).length > 0 ? (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
          {Object.entries(env)
            .map(([k, v]) => `${k}=${v}`)
            .join('\n')}
        </pre>
      ) : null}
      {configMap != null ? (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
          {JSON.stringify(configMap, null, 2)}
        </pre>
      ) : null}
      {endpoints && endpoints.length > 0 ? (
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/90 p-2 font-mono text-[11px] text-zinc-100">
          {JSON.stringify(endpoints, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}

function ResourceTable({ rows }: { rows: RuntimeAccessResourceRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-cns-muted">
        No persisted runtime rows yet. Deploy with the Go runner to populate resources.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-xs uppercase tracking-wide text-cns-label dark:border-zinc-700">
            <th className="py-2 pr-3 font-medium">Name</th>
            <th className="py-2 pr-3 font-medium">Runtime name</th>
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Ports</th>
            <th className="py-2 pr-3 font-medium">Internal URL</th>
            <th className="py-2 font-medium">External URL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.runtime_name}-${i}`} className="border-b border-zinc-100 dark:border-zinc-800">
              <td className="py-2 pr-3 font-medium text-zinc-900 dark:text-zinc-100">{r.name}</td>
              <td className="py-2 pr-3 font-mono text-xs text-zinc-700 dark:text-zinc-300">{r.runtime_name}</td>
              <td className="py-2 pr-3 text-xs">{r.status ?? '—'}</td>
              <td className="py-2 pr-3 font-mono text-[11px] text-zinc-600 dark:text-zinc-400">{formatPorts(r.ports)}</td>
              <td className="py-2 pr-3 break-all font-mono text-[11px] text-emerald-800 dark:text-emerald-300">
                {r.internal_url ?? '—'}
              </td>
              <td className="py-2 break-all font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                {r.external_url ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ServicesPanel({
  deploymentId,
  services,
  exposures,
  onRefresh,
}: {
  deploymentId: string;
  services: RuntimeAccessResourceRow[];
  exposures: ServiceExposureRow[] | undefined;
  onRefresh: () => Promise<void>;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const activeByResource = useMemo(() => {
    const m = new Map<string, ServiceExposureRow>();
    for (const e of exposures ?? []) {
      if (e.status === 'active') {
        m.set(e.runtime_resource_id, e);
      }
    }
    return m;
  }, [exposures]);

  if (services.length === 0) {
    return (
      <p className="text-sm text-cns-muted">
        No persisted runtime rows yet. Deploy with the Go runner to populate services.
      </p>
    );
  }

  async function onExpose(svcId: string) {
    setBusyId(svcId);
    try {
      await exposeDeploymentService(deploymentId, svcId, {});
      await onRefresh();
    } catch (e) {
      window.alert(e instanceof ApiError ? `${e.status} ${e.statusText}` : 'Expose failed');
    } finally {
      setBusyId(null);
    }
  }

  async function onUnexpose(svcId: string) {
    setBusyId(svcId);
    try {
      await unexposeDeploymentService(deploymentId, svcId);
      await onRefresh();
    } catch (e) {
      window.alert(e instanceof ApiError ? `${e.status} ${e.statusText}` : 'Unexpose failed');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="overflow-x-auto space-y-3">
      <p className="text-xs text-cns-muted">
        Expose registers how you can reach a workload from outside the lab network (host ports, port-forward, or future
        ingress). The control plane stores hints; your environment still runs the actual port-forward or tunnel.
      </p>
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-xs uppercase tracking-wide text-cns-label dark:border-zinc-700">
            <th className="py-2 pr-3 font-medium">Name</th>
            <th className="py-2 pr-3 font-medium">Runtime</th>
            <th className="py-2 pr-3 font-medium">Internal</th>
            <th className="py-2 pr-3 font-medium">Exposure</th>
            <th className="py-2 pr-3 font-medium">External</th>
            <th className="py-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {services.map((r, i) => {
            const rid = r.id;
            const active = rid ? activeByResource.get(rid) : undefined;
            const meta = active?.metadata;
            const cmds = meta && Array.isArray(meta.commands) ? (meta.commands as string[]) : [];
            return (
              <tr key={`${r.runtime_name}-${i}`} className="border-b border-zinc-100 align-top dark:border-zinc-800">
                <td className="py-2 pr-3 font-medium">{r.name}</td>
                <td className="py-2 pr-3 font-mono text-xs">{r.runtime_name}</td>
                <td className="py-2 pr-3 break-all font-mono text-[11px] text-emerald-800 dark:text-emerald-300">
                  {r.internal_url ?? '—'}
                </td>
                <td className="py-2 pr-3 text-xs">
                  {active ? (
                    <div>
                      <div className="font-semibold text-zinc-800 dark:text-zinc-100">{active.exposure_type}</div>
                      <div className="text-cns-muted">{active.status}</div>
                      {active.expires_at ? (
                        <div className="mt-0.5 text-[11px] text-cns-muted">expires {active.expires_at}</div>
                      ) : null}
                    </div>
                  ) : (
                    <span className="text-cns-muted">—</span>
                  )}
                </td>
                <td className="py-2 pr-3 break-all font-mono text-[11px]">
                  {active?.external_url ? (
                    <span className="text-emerald-800 dark:text-emerald-300">{active.external_url}</span>
                  ) : cmds.length > 0 ? (
                    <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded bg-zinc-950/90 p-1.5 text-[10px] text-zinc-100">
                      {cmds.join('\n')}
                    </pre>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="py-2">
                  {!rid ? (
                    <span className="text-xs text-cns-muted">No row id</span>
                  ) : active ? (
                    <button
                      type="button"
                      disabled={busyId === rid}
                      onClick={() => void onUnexpose(rid)}
                      className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                    >
                      {busyId === rid ? '…' : 'Unexpose'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busyId === rid}
                      onClick={() => void onExpose(rid)}
                      className="rounded-md border border-emerald-600 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-900 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/50 dark:text-emerald-100 dark:hover:bg-emerald-900/60"
                    >
                      {busyId === rid ? '…' : 'Expose'}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OperationsLogsPanel({
  deploymentId,
  services,
}: {
  deploymentId: string;
  services: RuntimeAccessResourceRow[];
}) {
  const selectable = useMemo(() => services.filter((s) => s.id), [services]);
  const [resourceId, setResourceId] = useState(selectable[0]?.id ?? '');
  const [tail, setTail] = useState(150);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!resourceId && selectable[0]?.id) setResourceId(selectable[0].id);
  }, [resourceId, selectable]);

  async function refreshAll() {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetchRuntimeDeploymentLogs(deploymentId, tail);
      setText(r.logs || JSON.stringify(r.items, null, 2));
    } catch (e) {
      setText('');
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function refreshOne() {
    if (!resourceId) {
      setErr('Select a service row with an id (deploy with Go runner to persist resources).');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await fetchRuntimeServiceLogs(deploymentId, resourceId, tail);
      setText(r.logs || JSON.stringify(r.items, null, 2));
    } catch (e) {
      setText('');
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-cns-muted">
        Fetches recent container or pod logs via the control plane (and Go runner when{' '}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">RUNTIME_EXECUTOR=go</code>).
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-cns-label">
          Service resource
          <select
            className="mt-1 block w-64 max-w-full rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            value={resourceId}
            onChange={(e) => setResourceId(e.target.value)}
          >
            <option value="">—</option>
            {selectable.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.runtime_name})
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-cns-label">
          Tail lines
          <input
            type="number"
            min={1}
            max={5000}
            className="mt-1 block w-24 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            value={tail}
            onChange={(e) => setTail(Number(e.target.value) || 100)}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void refreshAll()}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          Refresh all workloads
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void refreshOne()}
          className="rounded-md border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100 dark:hover:bg-emerald-900/50"
        >
          Refresh selected
        </button>
      </div>
      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}
      <textarea
        readOnly
        className="min-h-[220px] w-full resize-y rounded-lg border border-zinc-200 bg-zinc-950/90 p-3 font-mono text-[11px] text-zinc-100 dark:border-zinc-700"
        value={busy ? 'Loading…' : text}
        placeholder="Logs appear here after refresh."
      />
    </div>
  );
}

function OperationsHealthPanel({
  deploymentId,
  services,
}: {
  deploymentId: string;
  services: RuntimeAccessResourceRow[];
}) {
  const selectable = useMemo(() => services.filter((s) => s.id), [services]);
  const [resourceId, setResourceId] = useState(selectable[0]?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!resourceId && selectable[0]?.id) setResourceId(selectable[0].id);
  }, [resourceId, selectable]);

  async function run() {
    if (!resourceId) {
      setErr('Select a persisted service row.');
      return;
    }
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const r = await postRuntimeServiceHealth(deploymentId, resourceId);
      setResult(JSON.stringify(r, null, 2));
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-cns-muted">
        Runs an HTTP probe from inside the workload (Go runner). Requires member or owner on the project.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-cns-label">
          Service resource
          <select
            className="mt-1 block w-64 max-w-full rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            value={resourceId}
            onChange={(e) => setResourceId(e.target.value)}
          >
            <option value="">—</option>
            {selectable.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void run()}
          className="rounded-md border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100 dark:hover:bg-emerald-900/50"
        >
          {busy ? 'Running…' : 'Run health check'}
        </button>
      </div>
      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}
      {result ? (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-zinc-950/90 p-3 font-mono text-[11px] text-zinc-100 dark:border-zinc-700">
          {result}
        </pre>
      ) : null}
    </div>
  );
}

function OperationsTrafficPanel({
  deploymentId,
  services,
}: {
  deploymentId: string;
  services: RuntimeAccessResourceRow[];
}) {
  const selectable = useMemo(() => services.filter((s) => s.id), [services]);
  const [sourceId, setSourceId] = useState(selectable[0]?.id ?? '');
  const [target, setTarget] = useState('');
  const [protocol, setProtocol] = useState<'http' | 'ping'>('ping');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId && selectable[0]?.id) setSourceId(selectable[0].id);
  }, [sourceId, selectable]);

  async function run() {
    if (!sourceId) {
      setErr('Select a source service resource.');
      return;
    }
    if (!target.trim()) {
      setErr('Enter a target topology node id or http(s) URL.');
      return;
    }
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const r = await postRuntimeTrafficTest(deploymentId, {
        source_runtime_resource_id: sourceId,
        target: target.trim(),
        protocol,
      });
      setResult(JSON.stringify(r, null, 2));
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-cns-muted">
        Executes ping or HTTP from the source workload toward another node IP or an absolute URL (Go runner in-network
        exec). Requires member or owner.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-cns-label sm:col-span-1">
          Source service resource
          <select
            className="mt-1 block w-full rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
          >
            <option value="">—</option>
            {selectable.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-cns-label sm:col-span-1">
          Protocol
          <select
            className="mt-1 block w-full rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as 'http' | 'ping')}
          >
            <option value="ping">ping</option>
            <option value="http">http</option>
          </select>
        </label>
        <label className="text-xs text-cns-label sm:col-span-2">
          Target (node UUID or http URL)
          <input
            className="mt-1 block w-full rounded border border-zinc-300 bg-white px-2 py-1.5 font-mono text-xs dark:border-zinc-600 dark:bg-zinc-900"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="e.g. other-node-uuid or http://svc.namespace.svc.cluster.local:80/"
          />
        </label>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        className="rounded-md border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100 dark:hover:bg-emerald-900/50"
      >
        {busy ? 'Running…' : 'Run traffic test'}
      </button>
      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}
      {result ? (
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-zinc-950/90 p-3 font-mono text-[11px] text-zinc-100 dark:border-zinc-700">
          {result}
        </pre>
      ) : null}
    </div>
  );
}

export function RuntimeAccessPanel({ deploymentId }: { deploymentId: string | null }) {
  const [tab, setTab] = useState<TabId>('overview');
  const [data, setData] = useState<DeploymentRuntimeDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!deploymentId) return;
    setLoading(true);
    setErr(null);
    try {
      setData(await fetchDeploymentRuntime(deploymentId));
    } catch (e) {
      setData(null);
      setErr(e instanceof ApiError ? `${e.status} ${e.statusText}` : 'Could not load runtime access.');
    } finally {
      setLoading(false);
    }
  }, [deploymentId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!deploymentId) {
    return null;
  }

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Runtime access</h2>
          <p className="mt-1 max-w-3xl text-xs text-cns-muted">
            Use this deployment from your laptop, applications, CI/CD, other Kubernetes workloads, or the control-plane API.
            Resources are populated when the Go runner returns structured runtime metadata.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          {loading ? <Spinner className="h-3.5 w-3.5" /> : null}
          Refresh
        </button>
      </div>

      {err ? (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-1 border-b border-zinc-200 dark:border-zinc-700">
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={
              tab === id
                ? 'border-b-2 border-emerald-600 px-3 py-2 text-xs font-semibold text-emerald-800 dark:border-emerald-400 dark:text-emerald-200'
                : 'border-b-2 border-transparent px-3 py-2 text-xs font-medium text-cns-muted hover:text-zinc-900 dark:hover:text-zinc-100'
            }
          >
            {TAB_LABEL[id]}
          </button>
        ))}
      </div>

      <div className="mt-4 min-h-[120px]">
        {loading && !data ? (
          <div className="flex items-center gap-2 text-sm text-cns-muted">
            <Spinner className="h-4 w-4" />
            Loading runtime access…
          </div>
        ) : null}

        {data && tab === 'overview' ? (
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-cns-label">Access status</dt>
              <dd className="mt-1 text-sm font-medium">{data.status ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-cns-label">Deployment status</dt>
              <dd className="mt-1 text-sm font-medium">{data.deployment_status}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-cns-label">Runtime provider</dt>
              <dd className="mt-1 text-sm font-medium">{data.runtime_provider}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-cns-label">Namespace / network</dt>
              <dd className="mt-1 break-all font-mono text-xs">{data.namespace_or_network ?? '—'}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-cns-label">Active exposures</dt>
              <dd className="mt-1 text-sm font-medium">
                {(data.exposures ?? []).filter((e) => e.status === 'active').length}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-cns-label">Deployment id</dt>
              <dd className="mt-1 font-mono text-xs text-cns-muted">{data.deployment_id}</dd>
            </div>
          </dl>
        ) : null}

        {data && tab === 'nodes' ? <ResourceTable rows={data.nodes} /> : null}
        {data && tab === 'services' ? (
          <ServicesPanel
            deploymentId={deploymentId}
            services={data.services}
            exposures={data.exposures}
            onRefresh={load}
          />
        ) : null}

        {data && tab === 'endpoints' ? (
          data.endpoints.length === 0 ? (
            <p className="text-sm text-cns-muted">
              No internal endpoints recorded. Deploy with metadata from the runner, or check the Services tab.
            </p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.endpoints.map((ep, i) => (
                <li
                  key={`${ep.internal_url ?? i}-${i}`}
                  className="rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-950/40"
                >
                  <div className="text-xs font-semibold uppercase tracking-wide text-cns-label">
                    {ep.kind ?? 'endpoint'} · {ep.name ?? '—'}
                  </div>
                  <div className="mt-1 break-all font-mono text-[11px] text-emerald-800 dark:text-emerald-300">
                    {ep.internal_url ?? '—'}
                  </div>
                  {ep.external_url ? (
                    <div className="mt-1 break-all font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                      {ep.external_url}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )
        ) : null}

        {data && tab === 'instructions' && data.instructions ? (
          <div className="space-y-3">
            {(() => {
              const inst = data.instructions;
              return (
                [
                  ['local_dev', 'Connect from local machine'],
                  ['app_env', 'Use from app'],
                  ['ci_cd', 'Use in CI/CD'],
                  ['kubernetes', 'Use from Kubernetes'],
                  ['api', 'Control through API'],
                  ['exposed_services', 'Exposed services'],
                ] as const
              ).map(([key, heading]) => (
                <div key={key}>
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-cns-label">{heading}</div>
                  <InstructionSection modeKey={key} body={inst[key]} />
                </div>
              ));
            })()}
          </div>
        ) : null}

        {data && tab === 'instructions' && !data.instructions ? (
          <p className="text-sm text-cns-muted">No instructions available.</p>
        ) : null}

        {data && tab === 'op_logs' ? (
          <OperationsLogsPanel deploymentId={deploymentId!} services={data.services} />
        ) : null}
        {data && tab === 'op_health' ? (
          <OperationsHealthPanel deploymentId={deploymentId!} services={data.services} />
        ) : null}
        {data && tab === 'op_traffic' ? (
          <OperationsTrafficPanel deploymentId={deploymentId!} services={data.services} />
        ) : null}
      </div>
    </section>
  );
}
