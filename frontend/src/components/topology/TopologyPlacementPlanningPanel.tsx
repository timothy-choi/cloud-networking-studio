import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { listCredentialProfiles, type CredentialProfile } from '../../api/credentialProfiles';
import {
  generateInfrastructureDeployment,
  getTopologyPlacementPlan,
  getTopologyStrategyRecommendation,
  isStrategySelectable,
  type StrategyRecommendation,
  type TopologyPlacementPlan,
} from '../../api/topologyPlacement';
import { formatApiError } from '../../api/client';
import { Spinner } from '../Spinner';
import {
  DeploymentStrategySection,
  HostRecommendationSection,
  PlacementPlanSection,
  PlacementWarningsSection,
  ResourceEstimateSection,
} from './TopologyPlacementPlanSections';

interface Props {
  topologyId: string;
  projectId: string;
  readOnly?: boolean;
  onDeploymentGenerated?: (deploymentId: string) => void;
}

export function TopologyPlacementPlanningPanel({
  topologyId,
  projectId,
  readOnly = false,
  onDeploymentGenerated,
}: Props) {
  const [plan, setPlan] = useState<TopologyPlacementPlan | null>(null);
  const [strategy, setStrategy] = useState<StrategyRecommendation | null>(null);
  const [selectedStrategyId, setSelectedStrategyId] = useState('docker-vm');
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [machineType, setMachineType] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadPlan = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params = {
        provider: 'gcp' as const,
        ...(machineType.trim() ? { machine_type: machineType.trim() } : {}),
      };
      const [nextPlan, nextStrategy] = await Promise.all([
        getTopologyPlacementPlan(topologyId, params),
        getTopologyStrategyRecommendation(topologyId, params),
      ]);
      setPlan(nextPlan);
      setStrategy(nextStrategy);
      setSelectedStrategyId(nextStrategy.recommended_strategy);
    } catch (e) {
      setErr(formatApiError(e));
      setPlan(null);
      setStrategy(null);
    } finally {
      setLoading(false);
    }
  }, [topologyId, machineType]);

  useEffect(() => {
    void loadPlan();
  }, [loadPlan]);

  useEffect(() => {
    void listCredentialProfiles(projectId)
      .then((items) => {
        const gcp = items.filter((p) => p.provider === 'gcp');
        setProfiles(gcp);
        if (gcp.length > 0) setSelectedProfileId(gcp[0].id);
      })
      .catch(() => setProfiles([]));
  }, [projectId]);

  async function onGenerate() {
    if (readOnly) return;
    const profile = profiles.find((p) => p.id === selectedProfileId);
    if (!profile) {
      setErr('Select a GCP credential profile before generating infrastructure.');
      return;
    }
    const selected = strategy?.strategies.find((s) => s.id === selectedStrategyId);
    if (!selected || !isStrategySelectable(selected.status)) {
      setErr('Select an available deployment strategy before generating infrastructure.');
      return;
    }
    setBusy(true);
    setErr(null);
    setSuccess(null);
    try {
      const result = await generateInfrastructureDeployment(topologyId, {
        provider: 'gcp',
        template_id: selectedStrategyId,
        credentials_ref: profile.credentials_ref,
        ...(machineType.trim() ? { machine_type: machineType.trim() } : {}),
      });
      setPlan(result.placement_plan);
      const deploymentId = String((result.deployment as { id?: string }).id ?? '');
      onDeploymentGenerated?.(deploymentId);
      setSuccess(
        `Created deployment "${String((result.deployment as { name?: string }).name ?? 'infra')}" — ` +
          `strategy ${selectedStrategyId}, ` +
          `${String((result.deployment as { variables_json?: { machine_type?: string } }).variables_json?.machine_type ?? result.placement_plan.recommended_machine_type)}, ` +
          `${String((result.deployment as { variables_json?: { vm_count?: number } }).variables_json?.vm_count ?? 1)} VM(s).`,
      );
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }

  const hasCapacityWarning = plan?.warnings.some(
    (w) =>
      w.includes('Insufficient capacity') ||
      w.includes('exceed memory capacity') ||
      w.includes('exceed CPU capacity') ||
      w.includes('CPU demand exceeds') ||
      w.includes('exceed boot disk capacity'),
  );

  const selectedStrategy = strategy?.strategies.find((s) => s.id === selectedStrategyId);
  const strategyNotAvailable = !selectedStrategy || !isStrategySelectable(selectedStrategy.status);

  return (
    <div className="space-y-4">
      <p className="text-sm text-cns-muted">
        Estimates capacity, plans host placement, recommends a deployment strategy, and generates GCP
        infrastructure from the topology.
      </p>

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

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-cns-label">
          Override machine type (optional)
          <input
            value={machineType}
            onChange={(e) => setMachineType(e.target.value)}
            placeholder={plan?.recommended_machine_type ?? 'e2-medium'}
            className="mt-1 block w-40 rounded border px-2 py-1.5 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-900"
            disabled={readOnly}
          />
        </label>
        <button
          type="button"
          disabled={loading || busy}
          onClick={() => void loadPlan()}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600"
        >
          Refresh plan
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-cns-muted">
          <Spinner /> Loading placement plan…
        </div>
      ) : plan && strategy ? (
        <>
          <ResourceEstimateSection plan={plan} />
          <HostRecommendationSection plan={plan} />
          <PlacementPlanSection plan={plan} />
          <DeploymentStrategySection
            recommendation={strategy}
            selectedStrategyId={selectedStrategyId}
            onSelectStrategy={setSelectedStrategyId}
            readOnly={readOnly}
          />
          <PlacementWarningsSection warnings={[...plan.warnings, ...strategy.warnings.filter((w) => !plan.warnings.includes(w))]} />

          {!readOnly ? (
            <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
              <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Generate infrastructure deployment
              </h3>
              {profiles.length === 0 ? (
                <p className="mt-2 text-sm text-cns-muted">
                  Create a{' '}
                  <Link to="/credential-profiles" className="font-semibold text-emerald-700 underline dark:text-emerald-400">
                    GCP credential profile
                  </Link>{' '}
                  first.
                </p>
              ) : (
                <div className="mt-2 flex flex-wrap items-end gap-3">
                  <label className="text-xs text-cns-label">
                    Credential profile
                    <select
                      value={selectedProfileId}
                      onChange={(e) => setSelectedProfileId(e.target.value)}
                      className="mt-1 block min-w-[12rem] rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
                    >
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    disabled={busy || hasCapacityWarning || strategyNotAvailable}
                    onClick={() => void onGenerate()}
                    className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    {busy ? 'Generating…' : 'Generate infrastructure deployment'}
                  </button>
                </div>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
