# Topology Versioning and Deployment Profiles

Step 56 adds **topology versions** and **deployment profiles** so labs can be changed safely, compared, rolled back, and deployed with environment-specific overrides — without mutating the base topology graph when a profile is applied.

## Topology versions

A **version** is an immutable snapshot of:

- Topology metadata (`name`, `runtime_target`, `networking_mode`, `config`, …)
- All nodes and links (including `config` JSON per node)

Versions are created when:

| Source | When |
|--------|------|
| `manual` | User clicks **Save version** (API: `POST /topologies/{id}/versions`) |
| `autosave` | Topology graph is updated and `topology.config.autosave_versions` is `true` (off by default locally) |
| `deploy` | A deploy starts without an explicit `topology_version_id` (auto snapshot) |
| `rollback` | User restores an older snapshot |

Version numbers increment per topology (`1`, `2`, `3`, …).

### Rollback

`POST /topologies/{topology_id}/versions/{version_id}/rollback` (owners only):

1. Restores the topology graph from the selected snapshot
2. Creates a **new** version with `source=rollback`
3. Writes an audit log and notifies project members
4. **Does not deploy** — run Deploy separately to push runtime

### Diff

`GET /topologies/{id}/versions/{version_id}/diff?against={other_version_id}` returns structured changes:

- Nodes/links added, removed, changed
- Service/port changes
- Env var changes (**secret-like keys are masked**)
- Health check and runtime metadata changes

## Deployment profiles

A **profile** holds deploy-time overrides for a topology:

| Field | Purpose |
|-------|---------|
| `env_overrides` | Per-node env map merged at deploy |
| `image_tag_overrides` | Per-node image tag or full image ref |
| `replica_hints` / `resource_limits` | Hints stored in effective config |
| `expose_policy` | `restricted` vs `open` |
| `health_check_strictness` | `relaxed` vs `strict` |
| `runtime_provider_preference` | Override runtime target for this deploy |
| `debug_toolbox_enabled` | Debug tooling toggle |
| `ttl_hours` / `cleanup_policy` | Lifecycle metadata |

Profile types: `dev`, `staging`, `prod_like`, `custom`.

One profile per topology may be marked **default** (`POST …/profiles/{id}/set-default`, owners only).

## Deploy with effective config

`POST /topologies/{id}/deploy`:

```json
{
  "profile_id": "optional-uuid",
  "topology_version_id": "optional-uuid",
  "network_allocation_mode": "managed"
}
```

Behavior:

1. **Base snapshot** — selected version, or current topology (plus auto deploy-version when none selected)
2. **Profile overrides** merged in memory → `effective_config_json`
3. Base topology rows in Postgres are **not** modified by profile merges
4. Deployment record stores `topology_version_id`, `deployment_profile_id`, `effective_config_json`
5. Runtime planner uses the effective snapshot

Existing deploys without `profile_id` behave as before (plus an automatic deploy snapshot version).

### Example profiles

**Dev** — fast iteration:

```json
{
  "profile_type": "dev",
  "config_json": {
    "env_overrides": { "api": { "LOG_LEVEL": "debug" } },
    "debug_toolbox_enabled": true,
    "ttl_hours": 8,
    "expose_policy": "open"
  }
}
```

**Staging** — closer to production:

```json
{
  "profile_type": "staging",
  "config_json": {
    "image_tag_overrides": { "api": "staging-latest" },
    "health_check_strictness": "strict",
    "ttl_hours": 72
  }
}
```

**Prod-like** — owners notified on deploy start/success/failure:

```json
{
  "profile_type": "prod_like",
  "config_json": {
    "env_overrides": { "api": { "LOG_LEVEL": "warn" } },
    "expose_policy": "restricted",
    "health_check_strictness": "strict",
    "cleanup_policy": "aggressive"
  }
}
```

## Permissions

| Role | Versions | Profiles |
|------|----------|----------|
| Viewer | List/view/diff | List/view |
| Member | Create versions, deploy with profiles, create/update profiles | Same |
| Owner | Rollback | Delete profiles, set default |

## UI

On the topology detail page:

- **Versions** — list, compare, rollback (with confirmation)
- **Deployment profiles** — create/edit, set default
- **Deploy modal** — pick version, profile, allocation mode; shows warnings (including prod-like)

## Integrations

- **Audit logs** — version create/rollback, profile CRUD, deploy with version/profile metadata
- **Notifications** — rollback; prod-like deploy started/succeeded/failed
- **Integration outputs** — metadata includes `topology_version_id` and `deployment_profile_id`
- **Deployment timeline** — deploy started event includes version/profile ids

Secrets are never returned in diffs, audit metadata, effective config storage, or UI snapshots (masked as `[redacted]`).
