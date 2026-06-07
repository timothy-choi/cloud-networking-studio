import { useCallback, useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import {
  generateInfrastructureDeployment,
  getTopologyInfrastructureRecommendations,
  getTopologyResourceEstimate,
  type CapacityStatus,
  type InfrastructureRecommendations,
  type TopologyNodeResourceBreakdown,
  type TopologyResourceEstimate,
} from '../../api/topologyInfraPlanning';
import { listCredentialProfiles, type CredentialProfile } from '../../api/credentialProfiles';
import { Spinner } from '../Spinner';

function capacityTone(status: CapacityStatus): string {
  if (status === 'compatible') return 'text-emerald-700 dark:text-emerald-400';
  if (status === 'warning') return 'text-amber-700 dark:text-amber-400';
  return 'text-red-700 dark:text-red-400';
}

export function TopologyInfraPlanningPanel({
  topologyId,
  projectId,
  onDeploymentGenerated,
}: {
  topologyId: string;
  projectId?: string;
  onDeploymentGenerated?: (deploymentId: string) => void;
}) {
  const [estimate, setEstimate] = useState<TopologyResourceEstimate | null>(null);
  const [recommendations, setRecommendations] = useState<InfrastructureRecommendations | null>(null);
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [est, recs] = await Promise.all([
        getTopologyResourceEstimate(topologyId),
        getTopologyInfrastructureRecommendations(topologyId),
      ]);
      setEstimate(est);
      setRecommendations(recs);
      if (projectId) {
        const creds = await listCredentialProfiles(projectId);
        const gcpProfiles = creds.filter((p: CredentialProfile) => p.provider === 'gcp');
        setProfiles(gcpProfiles);
        if (gcpProfiles.length > 0) {
          setSelectedProfileId(gcpProfiles[0].id);
        }
      }
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [topologyId, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleGenerate() {
    if (!recommendations) return;
    setBusy(true);
    setErr(null);
    setSuccess(null);
    try {
      const profile = profiles.find((p) => p.id === selectedProfileId);
      const result = await generateInfrastructureDeployment(topologyId, {
        provider: recommendations.suggested_provider,
        template_id: recommendations.suggested_template_id,
        credentials_ref: profile?.credentials_ref,
        variables: recommendations.suggested_variables,
      });
      const deploymentId = String(result.deployment.id ?? '');
      setSuccess(`Generated infrastructure deployment (${result.capacity_check.status}).`);
      onDeploymentGenerated?.(deploymentId);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-cns-muted">
        <Spinner /> Loading topology resource planning…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {err ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {err}
        </div>
      ) : null}
      {success ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">
          {success}
        </div>
      ) : null}

      {estimate ? (
        <section className="rounded-lg border p-3 dark:border-zinc-700">
          <h3 className="text-sm font-semibold">Resource estimate</h3>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <div>
              <dt className="text-xs text-cns-muted">Total CPU</dt>
              <dd className="font-medium">{estimate.total_cpu}</dd>
            </div>
            <div>
              <dt className="text-xs text-cns-muted">Total memory</dt>
              <dd className="font-medium">{estimate.total_memory_mb} MB</dd>
            </div>
            <div>
              <dt className="text-xs text-cns-muted">Total disk</dt>
              <dd className="font-medium">{estimate.total_disk_gb} GB</dd>
            </div>
            <div>
              <dt className="text-xs text-cns-muted">Nodes / replicas</dt>
              <dd className="font-medium">
                {estimate.workload_node_count}/{estimate.node_count} · {estimate.total_replicas} replicas
              </dd>
            </div>
          </dl>
          {estimate.nodes.length > 0 ? (
            <ul className="mt-3 space-y-1 text-xs text-cns-muted">
              {estimate.nodes.map((node: TopologyNodeResourceBreakdown) => (
                <li key={node.node_id}>
                  {node.name}: {node.cpu_request} CPU, {node.memory_request_mb} MB, {node.disk_request_gb} GB disk,{' '}
                  {node.replicas} replica(s)
                  {node.resource_source ? `, source: ${node.resource_source}` : ''}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {recommendations ? (
        <section className="rounded-lg border p-3 dark:border-zinc-700">
          <h3 className="text-sm font-semibold">Infrastructure recommendations</h3>
          <div className="mt-2 grid gap-3 md:grid-cols-3">
            {(['gcp', 'aws', 'azure'] as const).map((provider) => (
              <div key={provider} className="rounded border px-2 py-2 text-sm dark:border-zinc-600">
                <div className="text-xs font-semibold uppercase text-cns-muted">{provider}</div>
                <ul className="mt-1 space-y-0.5 font-mono text-[11px]">
                  {(recommendations.recommendations[provider] ?? []).map((machine: string) => (
                    <li key={machine}>{machine}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {recommendations.rationale.length > 0 ? (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-cns-muted">
              {recommendations.rationale.map((line: string) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {recommendations ? (
        <section className="rounded-lg border p-3 dark:border-zinc-700">
          <h3 className="text-sm font-semibold">Compatibility preview</h3>
          <p className="mt-1 text-xs text-cns-muted">
            Suggested {recommendations.suggested_provider} ·{' '}
            <code className="font-mono">
              {String(recommendations.suggested_variables.machine_type ?? recommendations.suggested_variables.instance_type ?? '—')}
            </code>
          </p>
          <p className={`mt-2 text-sm ${capacityTone('compatible')}`}>
            Generated deployments run capacity validation at create/validate time.
          </p>
        </section>
      ) : null}

      <div className="flex flex-wrap items-end gap-3">
        {profiles.length > 0 ? (
          <label className="text-xs text-cns-label">
            GCP credential profile
            <select
              value={selectedProfileId}
              onChange={(e) => setSelectedProfileId(e.target.value)}
              className="mt-1 block min-w-[14rem] rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            >
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            Create a GCP credential profile to generate a cloud deployment draft.
          </p>
        )}
        <button
          type="button"
          disabled={busy || !recommendations || (profiles.length > 0 && !selectedProfileId)}
          onClick={() => void handleGenerate()}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Generating…' : 'Generate infrastructure deployment'}
        </button>
      </div>
    </div>
  );
}
