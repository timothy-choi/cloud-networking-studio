# Roadmap

Honest status of what exists today vs what is planned. This is a **portfolio / demo platform**, not a commercial multi-tenant SaaS.

---

## Implemented (verified in repo)

### Core platform

- [x] User registration, JWT auth, optional login requirement
- [x] Projects, memberships, roles (viewer / member / owner)
- [x] Email invitations (console/SMTP), accept/decline flow
- [x] API tokens with scopes
- [x] Topology CRUD — nodes, links, templates, React Flow studio
- [x] Flat and multi-segment (routed) Docker topologies
- [x] Deploy, destroy, deployment events, deployment timeline
- [x] Runtime inspection (topology + deployment scoped)
- [x] Reconcile and heal
- [x] Traffic tests (ping, HTTP) and failure injection (stop/restart)
- [x] Runtime terminal, exec, service exposure (Step 40+)
- [x] Integration outputs and downloadable integration files
- [x] IaC export: Docker Compose, Kubernetes, Terraform, Ansible (+ preview/archive)
- [x] Topology versioning, diff, rollback modes
- [x] Deployment profiles (env/image overrides)
- [x] Notifications, audit logs, onboarding checklist
- [x] Platform / project / deployment metrics
- [x] Go runtime executor (`cns-runner`) for production compose path
- [x] CI: pytest, frontend build/test, Docker image builds, compose validate
- [x] Staging + production GitHub Actions deploy workflows
- [x] Terraform (EC2/VPC), Ansible playbooks, prod smoke scripts

### Frontend pages

- [x] Dashboard, topology detail, templates, platform metrics/security, API tokens, notifications

---

## Near-term improvements (in progress / high priority)

- [ ] Broader automated test coverage for versioning/rollback edge cases
- [ ] Consolidate and keep ops docs in sync with workflow env vars
- [ ] Prometheus metrics export (hooks exist; full scrape config not productized)
- [ ] Email delivery hardening (SMTP templates, bounce handling) beyond console provider
- [ ] UI polish for deployment profiles and version diff (API complete)

---

## Experimental

- [x] Kubernetes `runtime_target` via Go runner — **works for simple labs only**
- [ ] Segmented multinet on Kubernetes runner (explicitly unsupported today)
- [ ] Ephemeral PR stacks (implemented in CI; not a hosted product feature)

Label anything Kubernetes-related as **experimental** in demos unless you operate your own cluster.

---

## Future ideas (not implemented)

- Multi-tenant billing, quotas beyond current rate limits
- Full Terraform/Ansible **apply** pipeline (today: export/download only)
- Bandwidth/latency emulation, advanced network policies
- Scheduled chaos / failure automation
- Real-time collaboration (multi-user editing on same topology)
- Managed HA control plane (multi-region, active-active)
- Native mobile app

---

## Out of scope (do not claim in interviews)

- Commercial SLA or 24/7 operations
- Fully managed Kubernetes-as-a-product for customers
- Global anycast / multi-region data plane
- SOC2 / formal compliance certification

---

## How to discuss in interviews

**Say:** control-plane patterns, Docker-backed labs, CI/CD to EC2, staging isolation, versioning/rollback, team RBAC, observability hooks.

**Avoid:** “production SaaS at scale” unless you clarify it is **your** operated demo environment with real HTTPS and smoke tests.

See also [RESUME_NOTES.md](RESUME_NOTES.md) · [recruiter-highlights.md](recruiter-highlights.md)
