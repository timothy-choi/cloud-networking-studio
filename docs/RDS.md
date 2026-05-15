# AWS RDS PostgreSQL (production)

This repository supports **optional** Amazon RDS for PostgreSQL so production data can live **outside** the EC2 host disk. **Local development** and **CI** continue to use the **Docker Compose** `postgres` service (see profile `localdb` below). **Ephemeral PR stacks** keep **`rds_enabled = false`** in Terraform unless you deliberately change that.

---

## Local Postgres vs RDS on EC2

| Mode | Where Postgres runs | `docker-compose.prod.yml` |
|------|---------------------|---------------------------|
| **Local / CI** | Container on the same host as the API | Use **`--profile localdb`** so the `postgres` service starts. Default `DATABASE_URL` uses hostname **`postgres`**. |
| **Production (Compose Postgres)** | Container on EC2 | Same as local: deploy writes `DATABASE_URL` pointing at **`postgres:5432`** and Compose uses **`--profile localdb`**. |
| **Production (RDS)** | Managed RDS in the same VPC as EC2 | Omit the profile so **only** API, UI, and Caddy run. **`DATABASE_URL`** points at the RDS endpoint (from Terraform outputs + GitHub secret password). |

The FastAPI app always reads **`DATABASE_URL`** from the environment ([`backend/app/core/config.py`](../backend/app/core/config.py)).

---

## Why use RDS?

- **Durability and backups:** RDS automated backups and snapshots are independent of the EC2 root volume or Compose volume lifecycle. Replacing or rebuilding the instance does not delete the database if RDS is unchanged.
- **Operational separation:** Database patching, storage, and failover patterns are AWS-managed compared to a single-node Docker volume.
- **Cost:** Even **`db.t4g.micro`** / **`db.t3.micro`** plus storage and backups incur **ongoing monthly charges** in addition to EC2, NAT (if any), and data transfer. Disable RDS in Terraform when you do not need it (`rds_enabled = false`, the default).

---

## Terraform (`infra/terraform`)

- **`rds_enabled`** (default `false`): when `true`, provisions a single-AZ PostgreSQL instance, DB subnet group (two public subnets in two AZs), and a security group allowing **only** the EC2 instance security group to connect on **5432**.
- **`rds_instance_class`**: default **`db.t4g.micro`** (override with **`db.t3.micro`** if your region/account prefers x86).
- **`rds_publicly_accessible`**: `false` (default) keeps the endpoint **private** to the VPC; set `true` only if you need a public DNS name (still restricted by the RDS security group to the EC2 SG on 5432).
- **Outputs:** `rds_address`, `rds_port`, `rds_database_name`, `rds_username` — **never** the password.

If **`rds_master_password`** is empty in Terraform variables, a password is **auto-generated** and stored in **Terraform state** only — **GitHub Actions production deploy** expects you to supply **`RDS_PASSWORD`** or **`POSTGRES_PASSWORD`** so Terraform and the EC2 **`.env`** stay aligned. Do **not** commit passwords.

---

## GitHub Actions and secrets

- **Repository variable** **`RDS_ENABLED`**: set to **`true`** to pass **`TF_VAR_rds_enabled=true`** on production **`terraform apply`**.
- **Secrets** (either is accepted; **`RDS_PASSWORD`** wins when both are set in the expression `RDS_PASSWORD || POSTGRES_PASSWORD`):
  - **`POSTGRES_PASSWORD`** — original name; used for Docker Postgres on EC2 and as the RDS master password when **`RDS_PASSWORD`** is unset.
  - **`RDS_PASSWORD`** — optional override when you want a dedicated secret name for RDS.

CI **backend tests** and **ephemeral** workflows do **not** enable RDS unless you change their Terraform inputs explicitly.

---

## Docker Compose profile `localdb`

From the repo root:

```bash
docker compose --profile localdb -f docker-compose.prod.yml up -d --build
```

Without the profile, **`postgres` is not started**; set **`DATABASE_URL`** to an external DSN (e.g. RDS) in **`.env`**.

See also [DEPLOYMENT.md](DEPLOYMENT.md) and [CICD_DEPLOYMENT.md](CICD_DEPLOYMENT.md).
