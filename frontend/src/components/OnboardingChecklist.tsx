import { Link } from 'react-router-dom';
import type { OnboardingStepState } from '../api/onboarding';
import { completeOnboardingStep, updateOnboardingStatus } from '../api/onboarding';
import { formatApiError } from '../api/client';
import { onboardingProgress, stepHref } from '../lib/onboardingUi';

type Props = {
  steps: OnboardingStepState[];
  hasSeenOnboarding: boolean;
  firstTopologyId: string | null;
  selectedProjectId: string | null;
  onOpenCreateProject: () => void;
  onRefresh: () => Promise<void>;
  demoBusy: boolean;
  onStartDemo: () => void;
};

export function OnboardingChecklist({
  steps,
  hasSeenOnboarding,
  firstTopologyId,
  selectedProjectId,
  onOpenCreateProject,
  onRefresh,
  demoBusy,
  onStartDemo,
}: Props) {
  const { done, total } = onboardingProgress(steps);

  async function markComplete(stepId: string) {
    try {
      await completeOnboardingStep(stepId);
      await onRefresh();
    } catch (e) {
      window.alert(formatApiError(e));
    }
  }

  async function markIntroRead() {
    try {
      await updateOnboardingStatus({ has_seen_onboarding: true });
      await onRefresh();
    } catch (e) {
      window.alert(formatApiError(e));
    }
  }

  return (
    <div className="rounded-xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50/90 to-white p-5 shadow-sm dark:border-emerald-900/50 dark:from-emerald-950/30 dark:to-zinc-900/80">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-emerald-950 dark:text-emerald-100">
            Guided path: first deploy in minutes
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-emerald-950/85 dark:text-emerald-100/85">
            Optional checklist for demos and interviews — about five minutes. Steps tick when the platform detects the
            matching action, or use <strong className="font-semibold">Mark done</strong> if you showed the step another way.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-emerald-900/10 px-3 py-1 text-xs font-semibold text-emerald-900 dark:bg-emerald-400/10 dark:text-emerald-200">
            {done}/{total} complete
          </span>
          {!hasSeenOnboarding ? (
            <button
              type="button"
              onClick={() => void markIntroRead()}
              className="rounded-lg border border-emerald-800/30 bg-white/80 px-3 py-1.5 text-xs font-medium text-emerald-900 hover:bg-white dark:border-emerald-700/50 dark:bg-zinc-900 dark:text-emerald-100 dark:hover:bg-zinc-800"
            >
              Mark intro as read
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={demoBusy}
          onClick={onStartDemo}
          title="Creates the “CNS Quick demo” project, clones the built-in client→service template, deploys, then opens the lab."
          className="rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-emerald-900 disabled:opacity-60 dark:bg-emerald-600 dark:hover:bg-emerald-500"
        >
          {demoBusy ? 'Starting demo…' : 'Start demo (optional)'}
        </button>
        <span className="self-center text-[11px] text-emerald-900/80 dark:text-emerald-200/80">
          Uses the same templates as the library — no duplicate lab logic.
        </span>
      </div>

      <ol className="mt-5 space-y-3">
        {steps.map((s) => {
          const href = stepHref(s.id, { firstTopologyId, selectedProjectId });
          return (
            <li
              key={s.id}
              className={`flex flex-wrap items-start gap-3 rounded-lg border px-3 py-2 text-sm ${
                s.completed
                  ? 'border-emerald-200 bg-white/80 dark:border-emerald-900/40 dark:bg-emerald-950/20'
                  : 'border-zinc-200 bg-white/60 dark:border-zinc-700 dark:bg-zinc-950/40'
              }`}
            >
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  s.completed
                    ? 'bg-emerald-600 text-white dark:bg-emerald-500'
                    : 'border border-zinc-300 text-zinc-500 dark:border-zinc-600 dark:text-zinc-400'
                }`}
                aria-hidden
              >
                {s.completed ? '✓' : ''}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-zinc-900 dark:text-zinc-50">{s.title}</div>
                <p className="mt-0.5 text-xs leading-relaxed text-cns-muted">{s.description}</p>
                {s.auto_detected ? (
                  <p className="mt-1 text-[10px] font-medium uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
                    Detected from your workspace
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {href ? (
                  <Link
                    to={href}
                    className="text-xs font-semibold text-emerald-800 underline hover:text-emerald-950 dark:text-emerald-300"
                  >
                    Go
                  </Link>
                ) : s.id === 'project' ? (
                  <button
                    type="button"
                    className="text-xs font-semibold text-emerald-800 underline dark:text-emerald-300"
                    onClick={onOpenCreateProject}
                  >
                    New project
                  </button>
                ) : null}
                {!s.completed ? (
                  <button
                    type="button"
                    className="text-[11px] font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
                    onClick={() => void markComplete(s.id)}
                  >
                    Mark done
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
