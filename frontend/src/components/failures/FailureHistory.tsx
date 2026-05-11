import type { FailureInjectionResponse } from '../../types/failure';

interface Props {
  failures: FailureInjectionResponse[];
  nodeNameById: Map<string, string>;
}

export function FailureHistory({ failures, nodeNameById }: Props) {
  const sorted = [...failures].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Failure injections</h3>
        <p className="text-xs text-cns-muted">Stop / restart / kill · auto-refreshed</p>
      </div>
      <div className="max-h-56 overflow-auto">
        {sorted.length === 0 ? (
          <p className="p-4 text-sm text-cns-muted">No injections recorded.</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-zinc-50 font-semibold text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Target</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {sorted.map((f) => (
                <tr key={f.id} className="font-mono text-[11px] text-zinc-700 dark:text-zinc-300">
                  <td className="whitespace-nowrap px-3 py-2 text-cns-muted">{formatTs(f.created_at)}</td>
                  <td className="px-3 py-2">{f.failure_type}</td>
                  <td className="px-3 py-2">{nodeNameById.get(f.target_node_id) ?? f.target_node_id.slice(0, 8)}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        f.status === 'succeeded'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : f.status === 'failed'
                            ? 'text-red-600 dark:text-red-400'
                            : 'text-amber-600 dark:text-amber-400'
                      }
                    >
                      {f.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { hour12: false });
  } catch {
    return iso;
  }
}
