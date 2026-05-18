# Runtime topology templates (Step 43)

Templates capture a **topology snapshot** (nodes, links, and topology-level runtime intent such as `runtime_target` and `networking_mode`) so teams can reuse lab layouts without re-drawing the graph.

## Model (`runtime_templates`)

| Field | Purpose |
|--------|---------|
| `id` | Primary key |
| `name`, `description` | Library metadata |
| `category`, `tags` | Organization and filtering |
| `owner_user_id` | Creator (`NULL` for built-in catalog rows) |
| `project_id` | `NULL` for private-only or catalog; set for **project** visibility |
| `visibility` | `private` (creator-only) or `project` (all project members) |
| `topology_snapshot` | Versioned JSON graph (see below) |
| `source_topology_id` | Optional FK to the topology the template was saved from |
| `slug` | When set, marks a **built-in** starter template (unique, not deletable) |
| `created_at`, `updated_at` | Audit |

Built-in starters (`slug` set): **client-service**, **gateway-api-db**, **failure-injection-lab**. They are inserted once at API bootstrap (idempotent by `slug`).

## Snapshot JSON (`version: 1`)

- `topology`: `name`, `description`, `runtime_target`, `networking_mode`, `config`
- `nodes`: each has stable string `id` (UUID string when saved from a real topology, or short keys in starters), plus `name`, `node_type`, `image`, `ip_address`, `config`
- `links`: `source_id`, `target_id` referencing node `id` values, plus link fields aligned with the topology API (`network_name`, `cidr`, `gateway`, `vlan_tag`, endpoint IPs, `config`)

Cloning generates **new** UUIDs for nodes and links and creates a **draft** topology in the target project.

## HTTP API

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/templates/from-topology/{topology_id}` | Body: `name`, optional `description`, `category`, `tags`, `visibility`. Requires **member or owner** on the topology’s project. |
| `GET` | `/templates` | Query: `project_id`, `category`, `q` (name contains). Returns visible templates. |
| `GET` | `/templates/{template_id}` | Includes `topology_snapshot`. |
| `POST` | `/templates/{template_id}/clone` | Body: optional `name`, `project_id` (defaults to first project). Requires **member or owner** on the target project. Creates topology. |
| `DELETE` | `/templates/{template_id}` | **Creator** or **project owner** (for project-scoped templates). Built-ins return **403**. |

## Permissions summary

| Role | List / GET | Save from topology | Clone | Delete |
|------|------------|-------------------|-------|--------|
| Viewer | Yes (project + catalog + own private N/A) | No | No | No |
| Member | Yes | Yes | Yes | Own templates only (not other members’ unless owner) |
| Owner | Yes | Yes | Yes | Own + any template in owned project (per delete rules) |

Delete: **template creator** always; **project owner** may delete templates that belong to their project (`project_id` matches). Built-in templates cannot be deleted.

## Frontend

- **Templates** page lists cards (category, tags, visibility, built-in badge).
- Topology detail includes **Save as template** (editors only).
- **Create topology from template** clones into a selected project and opens the new topology.

## Non-goals (this step)

- No changes to **deployment** or **runtime provider** logic.
- Templates are **not** live deployments; clone only creates intent (draft topology).
