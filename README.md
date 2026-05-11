# Cloud Networking Studio

Cloud Networking Studio is a cloud-native infrastructure and networking experimentation platform where users can design, deploy, observe, and test real distributed environments from the browser.

The platform will support visual topology creation, runtime deployment, virtual networking, traffic testing, failure injection, and observability.

## Initial MVP

The first version focuses on:

- Topology persistence
- Backend API
- Deployment planning
- Runtime provider abstraction
- Docker-based local runtime
- Deployment event tracking

## Long-Term Direction

Cloud Networking Studio is intended to grow into a platform ecosystem with pluggable runtime providers, networking providers, telemetry providers, and experimentation tools.

## Demo Flow

Repeatable end-to-end demos live under `scripts/` so you do not need to copy topology or deployment IDs by hand.

### Prerequisites

- **PostgreSQL** reachable via `DATABASE_URL` (e.g. start the compose service: `docker compose up -d postgres` then point at port **5433** if using the repo defaults).
- **`curl`** and **`jq`** on your PATH.
- **Docker Engine** on the same machine as the API if you want real containers, CNS networks, traffic tests, and failure injection against live workloads (the demo script still exercises the HTTP API without Docker, but runtime steps need the daemon).

### Start the backend

From the repository root (with `DATABASE_URL` set):

```bash
cd backend
pip install -r requirements.txt   # if needed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Override the API URL when not using localhost:8000:

```bash
export API_BASE=http://127.0.0.1:8000
```

### Run the full demo

```bash
./scripts/demo_full_flow.sh
```

The script creates a uniquely named topology and **10.x.0.0/24** subnet (random third octet), deploys an Alpine host and nginx service, runs ping + HTTP traffic tests, injects failures (stop service, restart host), reconciles and heals, lists failures and deployment events, destroys the deployment, and prints hints if Docker resources remain.

### Manual Docker cleanup

If labeled CNS resources remain after a demo or crash:

```bash
./scripts/cleanup_cns_docker.sh
```

This removes containers and networks carrying `label=cns.project=cloud-networking-studio`.

### What the demo proves

- **Design → deploy → observe**: topology CRUD, deployment, runtime inspection.
- **Traffic testing**: reachability between nodes on the CNS bridge.
- **Failure injection**: controlled stop/restart without arbitrary shell.
- **Operations**: reconciliation detects drift; heal attempts recovery.
- **Teardown**: deployment destroy drives provider cleanup (verify with optional Docker checks at end of the script).
