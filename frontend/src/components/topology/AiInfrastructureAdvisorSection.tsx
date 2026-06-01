import type { AiInfrastructureAdvice } from '../../api/topologyPlacement';
import { Spinner } from '../Spinner';

interface Props {
  advice: AiInfrastructureAdvice | null;
  loading: boolean;
  error: string | null;
  readOnly?: boolean;
  onRequestAdvice: () => void;
  onApplyMachineType?: (machineType: string) => void;
}

export function AiInfrastructureAdvisorSection({
  advice,
  loading,
  error,
  readOnly = false,
  onRequestAdvice,
  onApplyMachineType,
}: Props) {
  const overrides = advice?.recommended_overrides;
  const canApplyMachineType =
    Boolean(overrides?.machine_type_valid && overrides?.machine_type && onApplyMachineType);

  return (
    <section className="rounded-lg border border-violet-200 bg-violet-50/40 p-3 dark:border-violet-900 dark:bg-violet-950/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">AI advisor</h3>
        <span className="text-xs text-cns-muted">Advisory only — does not deploy infrastructure</span>
      </div>
      <p className="mt-1 text-xs text-cns-muted">
        Explains deterministic planner output and suggests optional overrides. You choose what to apply;
        backend validation still controls deployment.
      </p>

      {!readOnly ? (
        <button
          type="button"
          disabled={loading}
          onClick={onRequestAdvice}
          className="mt-3 rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-sm font-medium text-violet-900 dark:border-violet-700 dark:bg-violet-950 dark:text-violet-100"
        >
          {loading ? 'Getting advice…' : 'Get AI advice'}
        </button>
      ) : null}

      {loading ? (
        <div className="mt-3 flex items-center gap-2 text-sm text-cns-muted">
          <Spinner /> Analyzing planner output…
        </div>
      ) : null}

      {error ? (
        <p className="mt-3 text-sm text-red-700 dark:text-red-300">{error}</p>
      ) : null}

      {advice ? (
        <div className="mt-3 space-y-3 text-sm">
          <div>
            <p className="text-xs font-medium text-cns-label">Summary</p>
            <p className="mt-1 text-zinc-800 dark:text-zinc-200">{advice.summary}</p>
          </div>

          {advice.risks.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-cns-label">Risks</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-amber-900 dark:text-amber-200">
                {advice.risks.map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {advice.suggestions.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-cns-label">Suggestions</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-zinc-800 dark:text-zinc-200">
                {advice.suggestions.map((suggestion) => (
                  <li key={suggestion}>{suggestion}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {overrides?.machine_type || overrides?.strategy ? (
            <div>
              <p className="text-xs font-medium text-cns-label">Suggested overrides</p>
              <ul className="mt-1 space-y-1 font-mono text-xs">
                {overrides.machine_type ? (
                  <li>
                    machine_type: {overrides.machine_type}
                    {overrides.machine_type_valid ? (
                      <span className="ml-2 font-sans text-emerald-700 dark:text-emerald-400">valid</span>
                    ) : (
                      <span className="ml-2 font-sans text-amber-700 dark:text-amber-400">
                        not allowed by planner
                      </span>
                    )}
                  </li>
                ) : null}
                {overrides.strategy ? (
                  <li>
                    strategy: {overrides.strategy}
                    {overrides.strategy_valid ? (
                      <span className="ml-2 font-sans text-emerald-700 dark:text-emerald-400">valid</span>
                    ) : (
                      <span className="ml-2 font-sans text-amber-700 dark:text-amber-400">not apply-ready</span>
                    )}
                  </li>
                ) : null}
              </ul>
              {canApplyMachineType && !readOnly ? (
                <button
                  type="button"
                  onClick={() => onApplyMachineType?.(overrides!.machine_type!)}
                  className="mt-2 rounded border border-violet-300 px-2 py-1 text-xs font-medium dark:border-violet-700"
                >
                  Apply suggested machine type ({overrides!.machine_type})
                </button>
              ) : null}
            </div>
          ) : null}

          <div>
            <p className="text-xs font-medium text-cns-label">Explanation</p>
            <p className="mt-1 text-xs text-cns-muted">{advice.explanation}</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
