# Credential Profiles

Infrastructure deployments can authenticate to cloud providers using **encrypted credential profiles** stored per project, instead of relying on server-level environment variables.

## Overview

| Mechanism | Format | Typical use |
|-----------|--------|-------------|
| **Credential profile** (preferred) | `credential:<profile_uuid>` | End users deploying into their own GCP/AWS/Azure accounts |
| **Environment reference** (legacy) | `env:GOOGLE_APPLICATION_CREDENTIALS`, `env:GOOGLE_CREDENTIALS_JSON`, etc. | Platform-admin / shared production deployments |

Secrets are **encrypted at rest** (Fernet), **never returned by API responses**, and **masked in logs**. Temporary credential material is written only for the duration of Terraform execution, then cleaned up.

## Supported providers

| Provider | `credential_type` | Secret JSON shape |
|----------|-------------------|-------------------|
| GCP | `gcp_service_account_json` | Standard Google service account key JSON (`type`, `project_id`, `private_key`, `client_email`, …) |
| AWS | `aws_access_key` | `{"access_key_id":"…","secret_access_key":"…","region":"us-east-1"}` (region optional) |
| Azure | `azure_service_principal` | `{"client_id":"…","client_secret":"…","tenant_id":"…","subscription_id":"…"}` |

## API

All routes require authentication. Project-scoped routes enforce project membership; mutating routes require editor role.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects/{project_id}/credential-profiles` | List profiles (no secrets) |
| `POST` | `/projects/{project_id}/credential-profiles` | Create profile |
| `GET` | `/credential-profiles/{id}` | Get profile (no secret) |
| `PATCH` | `/credential-profiles/{id}` | Update name, metadata, or rotate secret |
| `DELETE` | `/credential-profiles/{id}` | Delete profile |
| `POST` | `/credential-profiles/{id}/validate` | Re-validate stored secret structure |

### Create example (GCP)

```http
POST /projects/{project_id}/credential-profiles
Content-Type: application/json

{
  "name": "My GCP SA",
  "provider": "gcp",
  "credential_type": "gcp_service_account_json",
  "secret": "{ \"type\": \"service_account\", ... }",
  "metadata": {}
}
```

Response includes `credentials_ref: "credential:123e4567-e89b-12d3-a456-426614174000"` for use in infrastructure deployments.

## Infrastructure deployment integration

When creating a deployment:

```json
{
  "provider": "gcp",
  "credentials_ref": "credential:123e4567-e89b-12d3-a456-426614174000",
  "template_id": "docker-vm",
  "name": "my-stack",
  "variables": { ... }
}
```

### Resolution flow

```
Infrastructure deployment
  → validate credentials_ref (ownership + provider match)
  → decrypt encrypted_secret
  → materialize temporary credentials (temp file or env vars)
  → Terraform init/plan/apply/destroy
  → secure cleanup (temp files removed)
  → update last_used_at + audit log
```

## Encryption

Set a dedicated encryption key in production:

```bash
CNS_CREDENTIAL_ENCRYPTION_KEY=<url-safe-base64-32-bytes>
```

If unset, `AUTH_SECRET_KEY` is used as a fallback (acceptable for dev; use a dedicated key in production).

Generate a key:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

## UI

- **Credentials** nav → `/credential-profiles` — create, edit, validate, and delete profiles per project.
- **Infrastructure Deployments** (topology page) — select a credential profile from the dropdown, or use manual `credentials_ref` for platform-admin env refs.

## Security

- Ownership validated via project membership before lookup or use.
- Cross-project access returns `404` (not `403`) to avoid profile ID enumeration.
- Audit events recorded on create, update, delete, validate, and use.
- RBAC-ready: editor role required for mutations; viewers can list/read.

## Migration from env refs

Platform operators can continue using:

- `env:GOOGLE_APPLICATION_CREDENTIALS`
- `env:GOOGLE_CREDENTIALS_JSON`

End users should create credential profiles and pass `credential:<profile_id>` instead of requiring server-side secret mounts.
