# Team collaboration (Step 54B)

Production-grade project membership via email invitations, role enforcement, and audit trails.

## Roles

| Role | Capabilities |
|------|----------------|
| **viewer** | View topology, deployments, runtime status, exports |
| **member** | Create/edit topologies, deploy, operate runtime (terminal, exec, expose) |
| **owner** | Manage members, invitations, project settings; delete project |

Enforced in `backend/app/services/access_control.py` and API token scopes.

## Invitation flow

1. Project **owner** sends `POST /projects/{project_id}/invitations` with `{ "email", "role" }`.
2. Backend stores a **hashed** token, sends email (console/SMTP), and creates an in-app notification if the email matches an existing user.
3. Invitee opens the accept URL from email:
   `https://app.cloudnetstudio.com/invitations/accept?token={id}.{secret}`
4. Signed-in user accepts or declines via:
   - `POST /invitations/{token}/accept`
   - `POST /invitations/{token}/decline`
5. On accept, a `ProjectMembership` row is created with the invited role.

### Invitation statuses

`pending` · `accepted` · `declined` · `expired` · `revoked`

Pending invites for the same `(project_id, email)` are blocked. Stale pending rows past `expires_at` are marked `expired` on list/accept.

### Security

- Raw tokens are returned **once** on create and in email links; only `token_hash` is stored.
- Accept/decline require the invited email when authenticated.
- Invite creation is rate-limited per user (`CNS_RATE_LIMIT_INVITE_PER_USER`).
- Listing invitations never exposes `token_hash` or raw tokens.

## API summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/projects/{id}/invitations` | owner | Create invitation |
| GET | `/projects/{id}/invitations` | member+ | List invitations |
| POST | `/projects/{id}/invitations/{invitation_id}/revoke` | owner | Revoke pending invite |
| POST | `/invitations/{token}/accept` | JWT (invitee) | Accept |
| POST | `/invitations/{token}/decline` | JWT (invitee) | Decline |
| PATCH | `/projects/{id}/members/{member_id}` | owner | Change role |
| DELETE | `/projects/{id}/members/{member_id}` | owner | Remove member |
| POST | `/projects/{id}/members/{member_id}/transfer-ownership` | owner | Transfer ownership |

The legacy `POST /projects/{id}/members/invite` direct-add endpoint was removed in favor of invitations.

## Ownership safety

- Cannot remove or demote the **last owner**.
- Ownership transfer requires the target to be an existing member.
- Transfer updates `project.owner_user_id`, audits, and notifies both parties.

## Audit events

| Action | When |
|--------|------|
| `project.invite.sent` | Invitation created |
| `project.invite.accepted` | Invitee joined |
| `project.invite.declined` | Invitee declined |
| `project.invite.revoked` | Owner revoked pending invite |
| `project.member.role_changed` | Role updated |
| `project.member.removed` | Member removed |
| `project.ownership.transferred` | Ownership transferred |

View project audit logs: `GET /projects/{project_id}/audit-logs`.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CNS_FRONTEND_APP_URL` | `https://app.cloudnetstudio.com` | Base URL for accept links in email |
| `CNS_INVITATION_EXPIRE_DAYS` | `7` | Pending invite lifetime |
| `CNS_RATE_LIMIT_INVITE_PER_USER` | `20` | Max invites per user per window |
| `EMAIL_PROVIDER` | `console` | `console` / `smtp` / `disabled` (see [NOTIFICATIONS_EMAIL.md](./NOTIFICATIONS_EMAIL.md)) |

Local dev works without SMTP when `EMAIL_PROVIDER=console` (default).

## Frontend

- **Dashboard → Team**: `ProjectMembersPanel` — active members, pending/expired/revoked invites, invite form, role changes, ownership transfer.
- **`/invitations/accept?token=...`**: Accept or decline page (`AcceptInvitationPage`).
