import type { TrafficTestResponse } from '../../types/traffic';

interface Props {
  tests: TrafficTestResponse[];
}

export function TrafficTestHistory({ tests }: Props) {
  const sorted = [...tests].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/80">
      <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Traffic test history</h3>
        <p className="text-xs text-zinc-500">Ping & HTTP runs · auto-refreshed</p>
      </div>
      <div className="max-h-64 overflow-auto">
        {sorted.length === 0 ? (
          <p className="p-4 text-sm text-zinc-500">No traffic tests yet.</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-zinc-50 font-semibold text-zinc-600 dark:bg-zinc-950 dark:text-zinc-400">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Latency</th>
                <th className="px-3 py-2">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {sorted.map((t) => (
                <tr key={t.id} className="font-mono text-[11px] text-zinc-700 dark:text-zinc-300">
                  <td className="whitespace-nowrap px-3 py-2 text-zinc-500">{formatTs(t.created_at)}</td>
                  <td className="px-3 py-2 uppercase">{t.test_type}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        t.status === 'succeeded'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-red-600 dark:text-red-400'
                      }
                    >
                      {t.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {t.result?.latency_ms != null ? `${t.result.latency_ms.toFixed(1)} ms` : '—'}
                  </td>
                  <td className="max-w-[180px] truncate px-3 py-2" title={t.result?.stdout}>
                    {t.result ? (t.result.success ? 'ok' : `exit ${t.result.exit_code}`) : '—'}
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
    return new Date(iso).toLocaleTimeString(undefined, { hour12: false });
  } catch {
    return iso;
  }
}
