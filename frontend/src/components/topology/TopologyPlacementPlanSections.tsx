import {
  formatHostUtilization,
  formatNodeResourceLine,
  isStrategySelectable,
  strategyStatusLabel,
  type DeploymentStrategy,
  type StrategyRecommendation,
  type TopologyPlacementPlan,
} from '../../api/topologyPlacement';

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
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Placement plan</h3>
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
