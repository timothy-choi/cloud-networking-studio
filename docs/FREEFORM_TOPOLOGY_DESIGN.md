# Freeform topology & node configuration

Cloud Networking Studio (CNS) supports **freeform topology design** as a backward-compatible add-on. Existing topology builder flows, canvas templates, runtime templates, deployments, Runtime Access, terminal, safe exec, and CLI/CI behavior are unchanged unless you explicitly set custom node fields.

## Goals

- Design **any topology** with optional per-node runtime intent (image, command, ports, env, …).
- **Presets prefill only** — every field remains editable before save and deploy.
- **Missing custom fields** fall back to the same defaults as legacy labs (nginx/busybox/alpine heuristics, port 80, etc.).

## Create topology

The dashboard **Create topology** dialog offers:

| Choice | Behavior |
|--------|----------|
| **Start blank** | Empty graph (same as before). Set name, runtime target, networking mode. |
| **Start from template** | Clone a row from the **Templates** library (`POST /templates/{id}/clone`). Optional name override. |

Canvas **append templates** (client/server, three-tier, …) and **Reset demo lab** are unchanged.

## Add node

Toolbar actions (Host, Service, Router, Switch) open **Add node**:

- **Start from preset** — fills role label, image, command, ports, etc. from built-in presets (`frontend/src/lib/nodePresets.ts`).
- **Custom node** — empty form.

Copy in the UI:

- “Start from preset or create custom node”
- “Presets are editable defaults”

The inspector uses the same fields for edits after the node exists.

## Node configuration fields

Stored on each `TopologyNode` (backward compatible):

| Field | Storage | Notes |
|-------|---------|-------|
| `name`, `node_type` | Top-level columns | Unchanged |
| `image` | Top-level column | Unchanged |
| `intent_ip` | `ip_address` column | Unchanged API name |
| `role_label` | `config.role_label` | Deploy label `cns.forwarding_role` when set |
| `command` | `config.command` | String or argv list; overrides image defaults |
| `ports` | `config.ports` | JSON array; drives Runtime Access URLs (default `:80`) |
| `env` | `config.env` | Object or `KEY=value` list → container env |
| `terminal_enabled` | `config.terminal_enabled` | Default **on**; `false` hides terminal target |
| `health_check` | `config.health_check` | Path string or JSON probe hint |
| `description` / notes | `config.description` | Documentation only |
| Canvas layout | `config.editor_position` | Unchanged |

Legacy nodes with only `editor_position` (or empty `config`) load and deploy as before.

## Deploy behavior

1. `build_deployment_plan()` attaches `runtime_config` parsed from each node’s `config`.
2. **Docker (Python executor)** and **Go runner** honor custom `command`, `env`, `role_label`, and `ports` when present.
3. If a field is absent, providers use existing heuristics (e.g. nginx → default entrypoint, routers → `sleep infinity`, port 80 in runtime_access).

No changes to validation rules for links, intent IPs, or multinet routers unless you override commands explicitly.

## Runtime Access

After deploy, **Nodes** tab rows include when available:

- Role label, image, command
- Ports, intent IP, runtime IP
- Terminal availability (from `terminal_enabled`)
- Internal / external URLs (primary port from custom ports or 80)

Terminal tab skips services with `terminal_enabled: false` in persisted metadata.

## API compatibility

- `TopologyNodeCreate` / `Update` / `Response` schemas are unchanged (`config` JSON blob).
- Templates snapshot/clone still copy `name`, `node_type`, `image`, `ip_address`, `config` — freeform keys round-trip automatically.
- Go runner `PlanNode` JSON adds optional fields (`role_label`, `command`, `ports`, `env`, …) with `omitempty` for older clients.

## Tests

- `backend/tests/test_node_runtime_config.py` — parsing & metadata
- `backend/tests/test_freeform_topology_deploy.py` — legacy deploy, custom ports, template clone
- `frontend/src/lib/nodeRuntimeConfig.test.ts` — UI merge/validation

Run:

```bash
cd backend && pytest tests/test_node_runtime_config.py tests/test_freeform_topology_deploy.py tests/test_topology_api.py tests/test_templates_api.py
cd frontend && npm run test && npm run build
```

## Related docs

- [RUNTIME_TEMPLATES.md](./RUNTIME_TEMPLATES.md) — persisted template library
- [architecture.md](./architecture.md) — control plane & runner overview
