import { Link } from 'react-router-dom';

const FEATURES = [
  {
    title: 'Topology builder',
    body: 'Design flat or multi-segment labs with hosts, routers, and services — persisted as a graph you can iterate on, save layout, and reopen later.',
  },
  {
    title: 'Templates & library',
    body: 'Starter graphs (client → service, tiers, routed segments) append to your lab without overwriting your work — same graphs the optional one-click demo uses.',
  },
  {
    title: 'Deployment runtime',
    body: 'Plan and deploy to a Docker-backed runtime: networks, containers, and live status from the control plane (Kubernetes optional where wired).',
  },
  {
    title: 'Runtime Access & operations',
    body: 'Endpoints, expose controls, traffic tests, health checks, allowlisted diagnostics, logs, and teardown — the “day-2” surface recruiters expect next to deploy.',
  },
  {
    title: 'Traffic tests',
    body: 'Run directed ICMP and HTTP checks between nodes to prove cross-segment paths after deploy.',
  },
  {
    title: 'Failure injection',
    body: 'Stop, restart, or kill workloads to exercise drift, then reconcile or heal against live state.',
  },
  {
    title: 'Observability dashboard',
    body: 'Metrics summary, deployment timelines, and event streams for demos and debugging.',
  },
  {
    title: 'Project-scoped workspaces',
    body: 'Organize topologies per project with JWT-scoped APIs and API tokens — same RBAC in the UI and CLI.',
  },
] as const;

const DEMO_STEPS = [
  { title: 'Register or sign in', detail: 'Creates a starter project so you land in a real workspace.' },
  { title: 'Open the Dashboard', detail: 'Optional: Start demo (optional) clones a built-in template, deploys, and opens the lab in one action.' },
  { title: 'Use Runtime Access', detail: 'Run ping/HTTP traffic tests, skim deployment events, then destroy when done.' },
  { title: 'Point to the docs', detail: 'docs/DEMO_GUIDE.md and docs/ARCHITECTURE.md carry the full interviewer script and system story.' },
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
            <div className="flex flex-wrap items-center justify-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700 dark:text-sky-400">Control plane</p>
              <span className="rounded-full border border-zinc-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-300">
                Portfolio & interview demo
              </span>
            </div>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-zinc-950 sm:text-5xl dark:text-zinc-50">
              Design, deploy, and test cloud network topologies
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-lg leading-relaxed text-zinc-600 dark:text-zinc-400">
              Cloud Networking Studio is a portfolio-grade API and UI: model networks as a persisted graph, apply it to a
              real Docker runtime, run synthetic traffic, inject failures, reconcile drift, and stream deployment events —
              the same story you would tell for a small slice of a cloud networking platform.
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

        <section className="border-b border-zinc-200 bg-zinc-50/80 px-4 py-12 dark:border-zinc-800 dark:bg-zinc-950/60">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-cns-label">Five-minute demo path</h2>
            <p className="mx-auto mt-3 max-w-2xl text-center text-sm text-zinc-600 dark:text-zinc-400">
              No memorized script required — the in-app checklist and repo docs carry the narrative. Use this order when
              someone is watching your screen.
            </p>
            <ol className="mt-8 grid gap-4 sm:grid-cols-2">
              {DEMO_STEPS.map((step, i) => (
                <li
                  key={step.title}
                  className="flex gap-3 rounded-xl border border-zinc-200 bg-white p-4 text-left shadow-sm dark:border-zinc-800 dark:bg-zinc-900/70"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-900 text-xs font-bold text-white dark:bg-zinc-100 dark:text-zinc-900">
                    {i + 1}
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">{step.title}</h3>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{step.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
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
          <div className="mx-auto max-w-4xl space-y-10">
            <div>
              <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-cns-label">Logical stack</h2>
              <p className="mx-auto mt-4 max-w-3xl text-center text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                Browsers and automation talk to <strong className="text-zinc-900 dark:text-zinc-200">FastAPI</strong>; the
                API persists intent in <strong className="text-zinc-900 dark:text-zinc-200">PostgreSQL</strong> and drives a
                runtime boundary (Docker today; optional Kubernetes). A <strong className="text-zinc-900 dark:text-zinc-200">Go runtime executor</strong> can sit beside the API for richer deploy and in-network checks — see{' '}
                <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-[11px] dark:bg-zinc-800">docs/ARCHITECTURE.md</code>{' '}
                in the repo for the full picture.
              </p>
            </div>
            <div>
              <h3 className="text-center text-xs font-semibold uppercase tracking-wide text-cns-label">Example production layout</h3>
              <p className="mx-auto mt-3 max-w-3xl text-center text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                One way this project is hosted in the wild: <strong className="text-zinc-900 dark:text-zinc-200">Vercel</strong>{' '}
                for the React SPA, <strong className="text-zinc-900 dark:text-zinc-200">FastAPI</strong> on EC2,{' '}
                <strong className="text-zinc-900 dark:text-zinc-200">Caddy</strong> for HTTPS,{' '}
                <strong className="text-zinc-900 dark:text-zinc-200">Docker</strong> for lab workloads, and{' '}
                <strong className="text-zinc-900 dark:text-zinc-200">Terraform</strong> for the VPC and instance — not
                required for local demos.
              </p>
              <ul className="mt-6 flex flex-wrap justify-center gap-3 text-xs font-medium">
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
          </div>
        </section>

        <section className="mx-auto max-w-3xl px-4 py-12">
          <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-cns-label">Documentation (in the repo)</h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-zinc-600 dark:text-zinc-400">
            Clone the project to read these paths alongside the running app — ideal for screen-sharing with audio off.
          </p>
          <ul className="mt-6 space-y-2 rounded-xl border border-zinc-200 bg-white p-4 font-mono text-xs text-zinc-800 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-200">
            <li>
              <span className="text-cns-muted">Walkthrough — </span>docs/DEMO_GUIDE.md
            </li>
            <li>
              <span className="text-cns-muted">System story — </span>docs/ARCHITECTURE.md
            </li>
            <li>
              <span className="text-cns-muted">Step-by-step UI/CLI — </span>docs/DEMO_SCRIPT.md
            </li>
            <li>
              <span className="text-cns-muted">Resume bullets — </span>docs/RESUME_NOTES.md
            </li>
          </ul>
        </section>

        <section className="mx-auto max-w-3xl px-4 py-16 text-center">
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Ready to try it?</h2>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Create a free workspace, use <strong className="font-semibold text-zinc-800 dark:text-zinc-200">Start demo (optional)</strong> on the
            Dashboard for a one-click lab, or open the topology studio to design from scratch.
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

      <footer className="border-t border-zinc-200 bg-white px-4 py-8 text-center text-xs leading-relaxed text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-500">
        <p>Cloud Networking Studio — demo control plane for learning, portfolios, and technical interviews.</p>
        <p className="mt-2 text-[11px] text-zinc-400 dark:text-zinc-600">
          After sign-in: Dashboard → optional Start demo → topology → Runtime Access. Repo: README.md + docs/DEMO_GUIDE.md.
        </p>
      </footer>
    </div>
  );
}
