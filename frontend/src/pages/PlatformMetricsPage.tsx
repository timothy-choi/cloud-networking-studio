import { Link } from 'react-router-dom';

import { PlatformMetricsCard } from '../components/metrics/PlatformMetricsCard';

export function PlatformMetricsPage() {
  return (
    <div className="space-y-6">
      <div>
        <Link to="/dashboard" className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Platform metrics
        </h1>
        <p className="mt-1 text-sm text-cns-muted">
          Cross-project observability: deployments, runtime health, quotas, cleanup, and API traffic.
        </p>
      </div>
      <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/80">
        <PlatformMetricsCard />
      </section>
    </div>
  );
}
