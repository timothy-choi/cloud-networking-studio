import { useEffect, useState } from 'react';

import { formatApiError } from '../../api/client';
import {
  downloadRuntimePackage,
  formatHostUtilization,
  formatNodeResourceLine,
  generateRuntimePackage,
  isStrategySelectable,
  runtimeDeploymentModelLabel,
  runtimeHostModelLabel,
  strategyStatusLabel,
  type CostCapacityAnalysis,
  type DeploymentStrategy,
  type PlacementConstraint,
  type RuntimePackageGenerateResponse,
  type RuntimeStrategyPlan,
  type StrategyRecommendation,
  type TopologyPlacementPlan,
} from '../../api/topologyPlacement';
import { Spinner } from '../Spinner';

export function ResourceEstimateSection({ plan }: { plan: TopologyPlacementPlan }) {
  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Resource estimate</h3>
      <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs text-cns-muted">Total CPU</dt>
          <dd className="font-medium">{plan.total_cpu} vCPU</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Total memory</dt>
          <dd className="font-medium">{plan.total_memory_mb} MB</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Total disk</dt>
          <dd className="font-medium">{plan.total_disk_gb} GB</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Placement units</dt>
          <dd className="font-medium">{plan.placement_unit_count}</dd>
        </div>
      </dl>
      {plan.nodes.length > 0 ? (
        <ul className="mt-3 space-y-1 font-mono text-xs text-zinc-800 dark:text-zinc-200">
          {plan.nodes.map((node) => (
            <li key={node.node_id}>{formatNodeResourceLine(node)}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-cns-muted">No workload nodes with resource metadata.</p>
      )}
    </section>
  );
}

export function HostRecommendationSection({ plan }: { plan: TopologyPlacementPlan }) {
  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Host recommendation</h3>
      <p className="mt-1 text-sm">
        <span className="font-medium">{plan.recommended_machine_type}</span>
        {' · '}
        {plan.recommended_host_count} host{plan.recommended_host_count === 1 ? '' : 's'}
      </p>
      <p className="mt-1 text-xs text-cns-muted">{plan.machine_rationale}</p>
    </section>
  );
}

export function PlacementPlanSection({ plan }: { plan: TopologyPlacementPlan }) {
  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Multi-Host Placement Plan</h3>
        <span className="text-xs text-cns-muted">Mode: {plan.placement_mode ?? 'first_fit'}</span>
      </div>
      {plan.hosts.length === 0 ? (
        <p className="mt-2 text-sm text-cns-muted">
          No hosts assigned. Add resource metadata to topology nodes (CPU, memory, replicas).
        </p>
      ) : (
        <div className="mt-3 space-y-4">
          {plan.hosts.map((host) => {
            const utilization = formatHostUtilization(host);
            return (
              <div key={host.host_index} className="rounded border border-zinc-100 p-3 dark:border-zinc-800">
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Host {host.host_index}</p>
                <p className="mt-1 text-xs text-cns-muted">
                  Machine type: <span className="font-mono">{host.machine_type}</span>
                </p>
                <div className="mt-2">
                  <p className="text-xs font-medium text-cns-label">Assigned nodes</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
                    {host.assigned_nodes.map((nodeName) => (
                      <li key={`${host.host_index}-${nodeName}`}>{nodeName}</li>
                    ))}
                  </ul>
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-xs text-cns-muted">CPU</dt>
                    <dd>{utilization.cpu}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-cns-muted">Memory</dt>
                    <dd>{utilization.memory}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-cns-muted">Disk</dt>
                    <dd>{utilization.disk}</dd>
                  </div>
                </dl>
                {host.utilization ? (
                  <dl className="mt-2 grid gap-2 text-xs text-cns-muted sm:grid-cols-3">
                    <div>
                      <dt>CPU utilization</dt>
                      <dd>{host.utilization.cpu_utilization ?? 0}%</dd>
                    </div>
                    <div>
                      <dt>Memory utilization</dt>
                      <dd>{host.utilization.memory_utilization ?? 0}%</dd>
                    </div>
                    <div>
                      <dt>Disk utilization</dt>
                      <dd>{host.utilization.disk_utilization ?? 0}%</dd>
                    </div>
                  </dl>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function PlacementWarningsSection({ warnings }: { warnings: string[] }) {
  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Warnings</h3>
      {warnings.length === 0 ? (
        <p className="mt-2 text-sm text-cns-muted">None</p>
      ) : (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-900 dark:text-amber-200">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function strategyById(strategies: DeploymentStrategy[], id: string): DeploymentStrategy | undefined {
  return strategies.find((s) => s.id === id);
}

export function RuntimeStrategySection({ plan }: { plan: RuntimeStrategyPlan | null }) {
  if (!plan) {
    return (
      <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Runtime strategy</h3>
        <p className="mt-2 text-sm text-cns-muted">Loading runtime strategy plan…</p>
      </section>
    );
  }

  const strategy = plan.runtime_strategy;
  const supported: string[] = [];
  if (plan.capabilities.runtime_target_generation) supported.push('Runtime target generation');
  if (plan.capabilities.external_deployment) supported.push('External deployment');
  if (plan.capabilities.multi_host) supported.push('Multi-host placement');

  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Runtime strategy</h3>
      <p className="mt-2 text-sm">
        <span className="font-mono font-medium">{plan.selected_runtime_strategy}</span>
        <span className="ml-2 text-xs text-cns-muted">({strategyStatusLabel(strategy.status)})</span>
      </p>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-cns-muted">Runtime provider</dt>
          <dd className="font-mono">{strategy.runtime_provider}</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Host model</dt>
          <dd>{runtimeHostModelLabel(strategy.host_model)}</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Deployment model</dt>
          <dd>{runtimeDeploymentModelLabel(strategy.deployment_model)}</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Placement hosts</dt>
          <dd>{plan.host_count}</dd>
        </div>
      </dl>

      <div className="mt-3">
        <p className="text-xs font-medium text-cns-label">Requirements</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
          {plan.runtime_target_requirements.map((item) => (
            <li key={item.key}>
              {item.label}
              {!item.required ? ' (optional)' : ''}: {item.description}
            </li>
          ))}
        </ul>
      </div>

      {supported.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-cns-label">Supported</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
            {supported.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {plan.unsupported_features.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-cns-label">Unsupported features</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-amber-900 dark:text-amber-200">
            {plan.unsupported_features.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {!plan.can_generate_infrastructure && plan.generation_block_reason ? (
        <p className="mt-3 text-xs text-amber-700 dark:text-amber-400">{plan.generation_block_reason}</p>
      ) : null}
    </section>
  );
}

export function RuntimePackageExportSection({
  topologyId,
  strategyId,
  provider = 'gcp',
  machineType,
  placementMode = 'first_fit',
  runtimePlan,
  readOnly = false,
}: {
  topologyId: string;
  strategyId: string;
  provider?: string;
  machineType?: string;
  placementMode?: string;
  runtimePlan: RuntimeStrategyPlan | null;
  readOnly?: boolean;
}) {
  const [pkg, setPkg] = useState<RuntimePackageGenerateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setPkg(null);
    setErr(null);
  }, [strategyId, topologyId, machineType, placementMode]);

  const planningOnly = runtimePlan?.runtime_strategy.status !== 'available';
  const buttonLabel = planningOnly ? 'Generate Planning Package' : 'Generate Runtime Package';

  async function onGenerate() {
    setLoading(true);
    setErr(null);
    try {
      const result = await generateRuntimePackage(topologyId, {
        strategy_id: strategyId,
        provider,
        placement_mode: placementMode,
        ...(machineType?.trim() ? { machine_type: machineType.trim() } : {}),
      });
      setPkg(result);
    } catch (e) {
      setErr(formatApiError(e));
      setPkg(null);
    } finally {
      setLoading(false);
    }
  }

  async function onDownload() {
    if (!pkg) return;
    setErr(null);
    try {
      await downloadRuntimePackage(pkg.package_id);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Runtime package export</h3>
      <p className="mt-2 text-sm text-cns-muted">
        Generate a downloadable deployment package for{' '}
        <span className="font-mono font-medium">{strategyId}</span>.
      </p>

      {planningOnly ? (
        <p className="mt-2 text-xs text-amber-800 dark:text-amber-300">
          Planning-only strategy — package includes placement artifacts and README but is not directly runnable.
        </p>
      ) : null}

      {!readOnly ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={loading || !runtimePlan}
            onClick={() => void onGenerate()}
            className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50 dark:bg-emerald-600 dark:hover:bg-emerald-500"
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <Spinner /> Generating…
              </span>
            ) : (
              buttonLabel
            )}
          </button>
          {pkg ? (
            <button
              type="button"
              onClick={() => void onDownload()}
              className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600"
            >
              Download ZIP
            </button>
          ) : null}
        </div>
      ) : null}

      {err ? <p className="mt-2 text-sm text-red-600 dark:text-red-400">{err}</p> : null}

      {pkg ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-cns-label">
            Generated package ({pkg.status}
            {pkg.planning_only ? ', planning only' : ''})
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 font-mono text-xs">
            {pkg.files.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
          {pkg.limitations.length > 0 ? (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-amber-900 dark:text-amber-200">
              {pkg.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function DeploymentStrategySection({
  recommendation,
  selectedStrategyId,
  onSelectStrategy,
  readOnly = false,
}: {
  recommendation: StrategyRecommendation;
  selectedStrategyId: string;
  onSelectStrategy: (strategyId: string) => void;
  readOnly?: boolean;
}) {
  const recommended = strategyById(recommendation.strategies, recommendation.recommended_strategy);

  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Deployment strategy</h3>
      <p className="mt-2 text-sm">
        Recommended:{' '}
        <span className="font-mono font-medium">{recommendation.recommended_strategy}</span>
        {recommended ? (
          <span className="ml-2 text-xs text-cns-muted">({strategyStatusLabel(recommended.status)})</span>
        ) : null}
      </p>
      {recommendation.reasons.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-cns-label">Why</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-zinc-800 dark:text-zinc-200">
            {recommendation.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {recommendation.alternatives.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-cns-label">Alternatives</p>
          <ul className="mt-1 space-y-1 text-sm">
            {recommendation.alternatives.map((altId) => {
              const alt = strategyById(recommendation.strategies, altId);
              return (
                <li key={altId} className="font-mono text-zinc-800 dark:text-zinc-200">
                  {altId}
                  {alt ? (
                    <span className="ml-2 font-sans text-xs text-cns-muted">
                      ({strategyStatusLabel(alt.status)})
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {!readOnly ? (
        <div className="mt-3">
          <label className="text-xs text-cns-label">
            Strategy for generation
            <select
              value={selectedStrategyId}
              onChange={(e) => onSelectStrategy(e.target.value)}
              className="mt-1 block min-w-[14rem] rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            >
              {recommendation.strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id} disabled={!isStrategySelectable(strategy.status)}>
                  {strategy.display_name} ({strategyStatusLabel(strategy.status)})
                </option>
              ))}
            </select>
          </label>
          {selectedStrategyId !== recommendation.recommended_strategy ? (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
              Overriding recommended strategy. Only available strategies can be applied.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function formatCurrencyRange(analysis: CostCapacityAnalysis): string {
  const { low, high, currency } = analysis.cost_estimate.estimated_monthly_cost;
  const symbol = currency === 'USD' ? '$' : `${currency} `;
  return `${symbol}${low}-${high}/month`;
}

function providerLabel(provider: string): string {
  const key = provider.trim().toLowerCase();
  if (key === 'gcp') return 'GCP';
  if (key === 'aws') return 'AWS';
  return provider;
}

export function CostCapacitySection({ analysis }: { analysis: CostCapacityAnalysis }) {
  const riskClass =
    analysis.scaling_risk.scaling_risk === 'HIGH'
      ? 'text-red-700 dark:text-red-300'
      : analysis.scaling_risk.scaling_risk === 'MEDIUM'
        ? 'text-amber-700 dark:text-amber-300'
        : 'text-emerald-700 dark:text-emerald-300';

  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Cost &amp; Capacity</h3>

      <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs text-cns-muted">Provider</dt>
          <dd className="font-medium">{providerLabel(analysis.cost_estimate.provider)}</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Machine</dt>
          <dd className="font-mono font-medium">{analysis.cost_estimate.machine_type}</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Hosts</dt>
          <dd className="font-medium">{analysis.cost_estimate.host_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-cns-muted">Estimated monthly cost</dt>
          <dd className="font-medium">{formatCurrencyRange(analysis)}</dd>
        </div>
      </dl>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <div>
          <p className="text-xs font-medium text-cns-label">Capacity</p>
          <ul className="mt-1 space-y-1 text-sm">
            <li>CPU: {analysis.capacity.cpu_utilization_percent}% used</li>
            <li>Memory: {analysis.capacity.memory_utilization_percent}% used</li>
            <li>Disk: {analysis.capacity.disk_utilization_percent}% used</li>
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium text-cns-label">Headroom</p>
          <ul className="mt-1 space-y-1 text-sm">
            <li>CPU: {analysis.headroom.cpu_headroom_percent}% remaining</li>
            <li>Memory: {analysis.headroom.memory_headroom_percent}% remaining</li>
            <li>Disk: {analysis.headroom.disk_headroom_percent}% remaining</li>
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium text-cns-label">Alternatives</p>
          <ul className="mt-1 space-y-1 text-sm">
            <li>Cheaper: {analysis.alternatives.cheaper_alternative ?? 'None'}</li>
            <li>Safer: {analysis.alternatives.safer_alternative ?? 'None'}</li>
          </ul>
        </div>
      </div>

      <div className="mt-3">
        <p className="text-xs font-medium text-cns-label">Scaling Risk</p>
        <p className={`mt-1 text-sm font-semibold ${riskClass}`}>{analysis.scaling_risk.scaling_risk}</p>
        {analysis.scaling_risk.reasons.length > 0 ? (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-amber-900 dark:text-amber-200">
            {analysis.scaling_risk.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

export function PlacementConstraintsSection({
  constraints,
  nodes,
  creating,
  deletingId = null,
  readOnly = false,
  form,
  onChangeForm,
  onCreate,
  onDelete,
}: {
  constraints: PlacementConstraint[];
  nodes: string[];
  creating: boolean;
  deletingId?: string | null;
  readOnly?: boolean;
  form: {
    constraint_type: PlacementConstraint['constraint_type'];
    node_a: string;
    node_b: string;
    preferred_host: string;
  };
  onChangeForm: (next: {
    constraint_type: PlacementConstraint['constraint_type'];
    node_a: string;
    node_b: string;
    preferred_host: string;
  }) => void;
  onCreate: () => void;
  onDelete: (constraintId: string) => void;
}) {
  return (
    <section className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Placement constraints</h3>
      {constraints.length > 0 ? (
        <ul className="mt-2 space-y-2 text-sm">
          {constraints.map((constraint) => (
            <li key={constraint.id} className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <span className="font-mono">{constraint.constraint_type}</span>: {constraint.node_a}
                {constraint.node_b ? ` / ${constraint.node_b}` : ''}
                {constraint.preferred_host ? ` -> Host ${constraint.preferred_host}` : ''}
              </span>
              {!readOnly ? (
                <button
                  type="button"
                  disabled={deletingId === constraint.id}
                  onClick={() => onDelete(constraint.id)}
                  className="rounded border border-zinc-300 px-2 py-0.5 text-xs text-red-700 dark:border-zinc-600 dark:text-red-300"
                >
                  {deletingId === constraint.id ? 'Removing…' : 'Remove'}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-cns-muted">None</p>
      )}

      {!readOnly ? (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-xs text-cns-label">
            Type
            <select
              value={form.constraint_type}
              onChange={(e) =>
                onChangeForm({ ...form, constraint_type: e.target.value as PlacementConstraint['constraint_type'] })
              }
              className="mt-1 block rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            >
              <option value="different_host">different_host</option>
              <option value="same_host">same_host</option>
              <option value="preferred_host">preferred_host</option>
            </select>
          </label>
          <label className="text-xs text-cns-label">
            Node A
            <input
              value={form.node_a}
              onChange={(e) => onChangeForm({ ...form, node_a: e.target.value })}
              list="placement-node-names"
              className="mt-1 block w-36 rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
            />
          </label>
          {form.constraint_type !== 'preferred_host' ? (
            <label className="text-xs text-cns-label">
              Node B
              <input
                value={form.node_b}
                onChange={(e) => onChangeForm({ ...form, node_b: e.target.value })}
                list="placement-node-names"
                className="mt-1 block w-36 rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              />
            </label>
          ) : (
            <label className="text-xs text-cns-label">
              Preferred host
              <input
                value={form.preferred_host}
                onChange={(e) => onChangeForm({ ...form, preferred_host: e.target.value })}
                type="number"
                min={1}
                className="mt-1 block w-24 rounded border px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
              />
            </label>
          )}
          <datalist id="placement-node-names">
            {nodes.map((node) => (
              <option key={node} value={node} />
            ))}
          </datalist>
          <button
            type="button"
            disabled={creating || !form.node_a.trim()}
            onClick={onCreate}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600"
          >
            {creating ? 'Adding...' : 'Add constraint'}
          </button>
        </div>
      ) : null}
    </section>
  );
}
