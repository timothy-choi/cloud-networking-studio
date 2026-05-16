import { Link } from 'react-router-dom';

const FEATURES = [
  {
    title: 'Topology builder',
    body: 'Design flat or multi-segment labs with hosts, routers, and services — persisted as a graph you can iterate on.',
  },
  {
    title: 'Deployment runtime',
    body: 'Plan and deploy to a Docker-backed runtime: networks, containers, and live status from the control plane.',
  },
  {
    title: 'Traffic tests',
    body: 'Run directed ICMP and HTTP checks between nodes to validate connectivity after deploy.',
  },
  {
    title: 'Failure injection',
    body: 'Stop, restart, or kill workloads to exercise resilience and observe how the stack responds.',
  },
  {
    title: 'Observability dashboard',
    body: 'Metrics summary, deployment timelines, and event streams for demos and debugging.',
  },
  {
    title: 'Project-scoped workspaces',
    body: 'Organize topologies per project with JWT-scoped APIs — ready for multi-tenant style workflows.',
  },
] as const;

export function HomePage() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="border-b border-zinc-200/80 bg-white/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <span className="text-lg font-semibold tracking-tight">Cloud Networking Studio</span>
          <nav className="flex flex-wrap items-center gap-2">
            <Link
              to="/login"
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-900"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="border-b border-zinc-200 bg-gradient-to-b from-white to-zinc-50 px-4 py-16 dark:border-zinc-800 dark:from-zinc-950 dark:to-zinc-950/80">
          <div className="mx-auto max-w-4xl text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700 dark:text-sky-400">Control plane</p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-zinc-950 sm:text-5xl dark:text-zinc-50">
              Design, deploy, and test cloud network topologies
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-lg leading-relaxed text-zinc-600 dark:text-zinc-400">
              Cloud Networking Studio is a portfolio-grade API and UI for modeling networks as graphs, pushing them to a
              real Docker runtime, running synthetic traffic, injecting failures, and streaming deployment events — like a
              small slice of a cloud networking platform.
            </p>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
              <Link
                to="/register"
                className="rounded-xl bg-zinc-900 px-6 py-3 text-sm font-semibold text-white shadow-lg hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
              >
                Create account
              </Link>
              <Link
                to="/login"
                className="rounded-xl border border-zinc-300 bg-white px-6 py-3 text-sm font-semibold text-zinc-900 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
              >
                Sign in
              </Link>
            </div>
            <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-500">
              New here? <span className="font-medium text-zinc-800 dark:text-zinc-200">Create an account</span> — you will
              be signed in automatically after registration.
            </p>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16">
          <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-cns-label">Capabilities</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <article
                key={f.title}
                className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
              >
                <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{f.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="border-y border-zinc-200 bg-white px-4 py-14 dark:border-zinc-800 dark:bg-zinc-900/40">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-cns-label">Architecture</h2>
            <p className="mx-auto mt-4 max-w-3xl text-center text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
              Typical production layout: <strong className="text-zinc-900 dark:text-zinc-200">Vercel</strong> hosts the
              React SPA, <strong className="text-zinc-900 dark:text-zinc-200">FastAPI</strong> on EC2 exposes the control
              plane, <strong className="text-zinc-900 dark:text-zinc-200">Caddy</strong> terminates HTTPS, the{' '}
              <strong className="text-zinc-900 dark:text-zinc-200">Docker</strong> engine runs lab workloads, and{' '}
              <strong className="text-zinc-900 dark:text-zinc-200">Terraform</strong> provisions the VPC and instance.
            </p>
            <ul className="mt-8 flex flex-wrap justify-center gap-3 text-xs font-medium">
              {['Vercel frontend', 'FastAPI backend', 'Docker runtime', 'Terraform EC2', 'Caddy HTTPS'].map((x) => (
                <li
                  key={x}
                  className="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300"
                >
                  {x}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="mx-auto max-w-3xl px-4 py-16 text-center">
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Ready to try it?</h2>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Create a free workspace, then open the topology studio to design your first lab.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              to="/register"
              className="rounded-xl bg-zinc-900 px-6 py-3 text-sm font-semibold text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
            >
              Get started — Create account
            </Link>
            <Link
              to="/login"
              className="rounded-xl border border-zinc-300 px-6 py-3 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              Sign in
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-zinc-200 bg-white px-4 py-8 text-center text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-500">
        Cloud Networking Studio — demo control plane for learning and portfolios.
      </footer>
    </div>
  );
}
