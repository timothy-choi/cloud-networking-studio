import type { ReactNode } from 'react';

export interface TopologyTemplateAction {
  id: string;
  label: string;
  run: () => void;
}

export interface TopologyToolbarProps {
  busy: string | null;
  /** Parent-page runtime action — disables topology edits to avoid races. */
  locked?: boolean;
  nodeCount: number;
  hasSelection: boolean;
  deployBlocked?: boolean;
  deployBlockReasons?: string[];
  deployWarnings?: string[];
  onAddHost: () => void;
  onAddService: () => void;
  onAddRouter: () => void;
  onAddSwitch: () => void;
  onAutoLayout: () => void;
  onSaveTopology: () => void;
  onDeploy: () => void;
  onClear: () => void;
  onResetDemoLab: () => void;
  onDeleteSelection: () => void;
  onFit: () => void;
  templates: TopologyTemplateAction[];
  /** Click two nodes to connect (fallback when handle-drag is awkward). */
  linkMode?: boolean;
  linkDraftSourceId?: string | null;
  linkDraftSourceName?: string | null;
  onToggleLinkMode?: () => void;
}

function Btn({
  children,
  onClick,
  disabled,
  variant = 'default',
  title,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'default' | 'primary' | 'danger' | 'subtle';
  title?: string;
}) {
  const cls =
    variant === 'primary'
      ? 'border-emerald-700/50 bg-emerald-950/60 text-emerald-50 hover:bg-emerald-900/70'
      : variant === 'danger'
        ? 'border-red-800/60 bg-red-950/40 text-red-100 hover:bg-red-950/70'
        : variant === 'subtle'
          ? 'border-zinc-700 bg-zinc-900/80 text-zinc-300 hover:bg-zinc-800'
          : 'border-zinc-600 bg-zinc-900 text-zinc-100 hover:bg-zinc-800';
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1.5 text-xs font-medium shadow-sm disabled:cursor-not-allowed disabled:border-zinc-600 disabled:bg-zinc-950/75 disabled:text-zinc-300 disabled:saturate-75 ${cls}`}
    >
      {children}
    </button>
  );
}

export function TopologyToolbar({
  busy,
  locked = false,
  nodeCount,
  hasSelection,
  deployBlocked = false,
  deployBlockReasons = [],
  deployWarnings = [],
  onAddHost,
  onAddService,
  onAddRouter,
  onAddSwitch,
  onAutoLayout,
  onSaveTopology,
  onDeploy,
  onClear,
  onResetDemoLab,
  onDeleteSelection,
  onFit,
  templates,
  linkMode = false,
  linkDraftSourceId = null,
  linkDraftSourceName = null,
  onToggleLinkMode,
}: TopologyToolbarProps) {
  const d = busy !== null || locked;
  const clutter = nodeCount >= 16;
  const deployDisabled = d || deployBlocked;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-zinc-700/80 bg-gradient-to-b from-zinc-900 to-zinc-950 p-3 shadow-lg">
      {clutter ? (
        <div className="rounded-md border border-amber-800/50 bg-amber-950/35 px-2.5 py-2 text-[11px] leading-snug text-amber-100">
          Large topology ({nodeCount} nodes). Consider removing unused nodes or using auto layout before deploy.
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-cns-inverse-label">Add</span>
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

      {onToggleLinkMode ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-2">
          <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-cns-inverse-label">
            Connect
          </span>
          <Btn variant={linkMode ? 'primary' : 'default'} disabled={d} onClick={onToggleLinkMode}>
            {linkMode ? 'Link mode on' : 'Link mode'}
          </Btn>
          {linkMode ? (
            <span className="max-w-[14rem] text-[10px] leading-snug text-cns-inverse-muted">
              {linkDraftSourceId
                ? `Source: ${linkDraftSourceName ?? linkDraftSourceId.slice(0, 8)}… — click target node`
                : 'Click source node, then target node'}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-2">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-cns-inverse-label">Layout</span>
        <Btn disabled={d} onClick={onAutoLayout}>
          Auto layout
        </Btn>
        <Btn disabled={d} onClick={onFit}>
          Zoom fit
        </Btn>
        <Btn variant="subtle" disabled={d || !hasSelection} onClick={onDeleteSelection}>
          Delete selected
        </Btn>
        <label className="ml-auto flex items-center gap-2 text-[11px] text-cns-inverse-muted">
          <span className="hidden sm:inline">Use template</span>
          <select
            className="max-w-[13rem] rounded-md border border-zinc-600 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-100"
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
            <option value="">Optional — append pattern…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-2">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-cns-inverse-label">Topology</span>
        <Btn disabled={d} onClick={onSaveTopology} title="Writes canvas positions to the API. Use inspector Apply to save name, image, IP, and link CIDR edits.">
          Save layout
        </Btn>
        {deployBlocked && deployBlockReasons.length > 0 ? (
          <div className="w-full rounded-md border border-amber-800/50 bg-amber-950/40 px-2 py-1.5 text-[10px] leading-snug text-amber-100">
            <span className="font-semibold">Deploy blocked:</span> {deployBlockReasons.join(' ')}
          </div>
        ) : null}
        {!deployBlocked && deployWarnings.length > 0 ? (
          <div className="w-full rounded-md border border-sky-900/40 bg-sky-950/30 px-2 py-1.5 text-[10px] leading-snug text-sky-100">
            <span className="font-semibold">Before deploy:</span> {deployWarnings.join(' ')}
          </div>
        ) : null}
        <Btn
          variant="primary"
          disabled={deployDisabled}
          onClick={onDeploy}
          title={
            deployBlocked
              ? deployBlockReasons.join(' ')
              : deployWarnings.length
                ? 'Deploy enabled — review warnings above.'
                : undefined
          }
        >
          Deploy to runtime
        </Btn>
        <Btn variant="danger" disabled={d} onClick={onClear}>
          Clear all
        </Btn>
        <Btn variant="subtle" disabled={d} onClick={onResetDemoLab} title="Replaces graph with a small sample (host + service + link)">
          Replace with sample lab
        </Btn>
        {busy ? (
          <span className="ml-auto font-mono text-[10px] text-sky-400/90">Working: {busy}…</span>
        ) : null}
      </div>
    </div>
  );
}
