import { useState, type ReactNode } from 'react';

export function CollapsibleSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-semibold text-zinc-900 hover:bg-zinc-50 dark:text-zinc-100 dark:hover:bg-zinc-800/80"
      >
        <span>{title}</span>
        <span className="text-xs font-normal text-cns-muted">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open ? <div className="border-t border-zinc-200 px-4 pb-4 pt-2 dark:border-zinc-800">{children}</div> : null}
    </div>
  );
}
