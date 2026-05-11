import type { ReactNode } from 'react';

export interface TopologyTemplateAction {
  id: string;
  label: string;
  run: () => void;
}

export interface TopologyToolbarProps {
  busy: string | null;
  onAddHost: () => void;
  onAddService: () => void;
  onAddRouter: () => void;
  onAddSwitch: () => void;
  onAutoLayout: () => void;
  onSaveTopology: () => void;
  onDeploy: () => void;
  onClear: () => void;
  onFit: () => void;
  templates: TopologyTemplateAction[];
}

function Btn({
  children,
  onClick,
  disabled,
  variant = 'default',
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'default' | 'primary' | 'danger';
}) {
  const cls =
    variant === 'primary'
      ? 'border-emerald-700/50 bg-emerald-950/60 text-emerald-50 hover:bg-emerald-900/70'
      : variant === 'danger'
        ? 'border-red-800/60 bg-red-950/40 text-red-100 hover:bg-red-950/70'
        : 'border-zinc-600 bg-zinc-900 text-zinc-100 hover:bg-zinc-800';
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1.5 text-xs font-medium shadow-sm disabled:opacity-45 ${cls}`}
    >
      {children}
    </button>
  );
}

export function TopologyToolbar({
  busy,
  onAddHost,
  onAddService,
  onAddRouter,
  onAddSwitch,
  onAutoLayout,
  onSaveTopology,
  onDeploy,
  onClear,
  onFit,
  templates,
}: TopologyToolbarProps) {
  const d = busy !== null;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-zinc-700/80 bg-gradient-to-b from-zinc-900 to-zinc-950 p-3 shadow-lg">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Add
        </span>
        <Btn disabled={d} onClick={onAddHost}>
          Host
        </Btn>
        <Btn disabled={d} onClick={onAddService}>
          Service
        </Btn>
        <Btn disabled={d} onClick={onAddRouter}>
          Router
        </Btn>
        <Btn disabled={d} onClick={onAddSwitch}>
          Switch
        </Btn>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-2">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Layout
        </span>
        <Btn disabled={d} onClick={onAutoLayout}>
          Auto layout
        </Btn>
        <Btn disabled={d} onClick={onFit}>
          Zoom fit
        </Btn>
        <label className="ml-auto flex items-center gap-2 text-[11px] text-zinc-400">
          <span className="hidden sm:inline">Template</span>
          <select
            className="max-w-[11rem] rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-100"
            disabled={d}
            defaultValue=""
            onChange={(e) => {
              const id = e.target.value;
              e.target.value = '';
              if (!id) return;
              const t = templates.find((x) => x.id === id);
              t?.run();
            }}
          >
            <option value="">Quick create…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-2">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Topology
        </span>
        <Btn disabled={d} onClick={onSaveTopology}>
          Save topology
        </Btn>
        <Btn variant="primary" disabled={d} onClick={onDeploy}>
          Deploy topology
        </Btn>
        <Btn variant="danger" disabled={d} onClick={onClear}>
          Clear all
        </Btn>
        {busy ? (
          <span className="ml-auto font-mono text-[10px] text-sky-400/90">Working: {busy}…</span>
        ) : null}
      </div>
    </div>
  );
}
