# Notifications and email (Step 54A)

Cloud Networking Studio includes an in-app notification inbox and a pluggable email layer for future team invitations, runtime alerts, and security notices.

## Notification model

Table: `notifications`

| Field | Description |
|-------|-------------|
| `user_id` | Recipient (nullable for project broadcasts) |
| `project_id` | Optional project context |
| `type` | Machine-readable category (e.g. `deployment.failed`) |
| `title` / `message` | User-facing copy |
| `status` | `unread`, `read`, or `archived` |
| `severity` | `info`, `success`, `warning`, or `error` |
| `metadata` | JSON (links, IDs — secrets are scrubbed) |
| `created_at` / `read_at` | Timestamps |

### API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications` | List visible notifications |
| GET | `/notifications/unread-count` | Unread badge count |
| POST | `/notifications/{id}/read` | Mark one read |
| POST | `/notifications/read-all` | Mark all read |
| POST | `/notifications/{id}/archive` | Archive one |

Users see notifications where `user_id` matches their account, or project-scoped rows (`user_id` null) for projects they belong to.

### Service helpers

- `create_notification(...)`
- `notify_user(...)`
- `notify_project_members(...)`
- `notify_project_owners(...)`

Hooked today for: deployment success/failure, quota exceeded, cleanup completed, API token create/revoke, terminal opened, IaC export download.

Audit actions: `notification.created`, `email.sent`, `email.failed`.

## Email providers

Configure with environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_PROVIDER` | `console` | `console`, `smtp`, or `disabled` |
| `SMTP_HOST` | `localhost` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | empty | Auth user |
| `SMTP_PASSWORD` | empty | Auth password (never logged) |
| `SMTP_FROM_EMAIL` | `cns@localhost` | From address |
| `SMTP_USE_TLS` | `true` | STARTTLS |

### Development / tests

- **`console`** (default): logs email to the `cns.email` logger; no SMTP required.
- **`disabled`**: skips sending; notifications still work in-app.
- Pytest sets `EMAIL_PROVIDER=console` in `conftest.py`.

Email failures are logged and audit-recorded but **never block** the main API request.

## SMTP production setup

1. Set `EMAIL_PROVIDER=smtp`
2. Provide real `SMTP_*` values via `.env` or your orchestrator secrets
3. Restart the backend

SendGrid, Resend, and other HTTP providers are not implemented yet — SMTP is the optional production path.

## Templates

Basic text/HTML templates live in `backend/app/services/email_templates.py`:

- Deployment failed / succeeded
- Quota exceeded
- API token created / revoked
- Export completed
- Project invitation **placeholder** (team invites not implemented yet)

## Frontend

- Header **notification bell** with unread count, recent items, mark read, archive, and links from metadata
- **`/notifications`** page for full history

## Future: team invitations

When Step 54B+ adds invitations, reuse:

- `notify_user` / `notify_project_members`
- `project_invitation_placeholder` email template
- Console provider in dev; SMTP in production

No invitation endpoints are shipped in Step 54A.
