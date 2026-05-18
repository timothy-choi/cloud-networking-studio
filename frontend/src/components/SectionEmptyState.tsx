import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Props = {
  icon?: ReactNode;
  title: string;
  description: string;
  primaryAction?: { label: string; onClick?: () => void; to?: string };
  secondaryHint?: ReactNode;
};

export function SectionEmptyState({ icon, title, description, primaryAction, secondaryHint }: Props) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50/80 p-8 text-center dark:border-zinc-700 dark:bg-zinc-950/40">
      {icon ? <div className="text-3xl text-zinc-400 dark:text-zinc-600">{icon}</div> : null}
      <h3 className="mt-3 text-base font-semibold text-zinc-900 dark:text-zinc-50">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-cns-muted">{description}</p>
      {primaryAction ? (
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          {primaryAction.to ? (
            <Link
              to={primaryAction.to}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
            >
              {primaryAction.label}
            </Link>
          ) : (
            <button
              type="button"
              onClick={primaryAction.onClick}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
            >
              {primaryAction.label}
            </button>
          )}
        </div>
      ) : null}
      {secondaryHint ? <div className="mt-4 text-xs text-cns-muted">{secondaryHint}</div> : null}
    </div>
  );
}
