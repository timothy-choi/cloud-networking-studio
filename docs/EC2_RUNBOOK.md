# EC2 deployment runbook (single instance)

Deploy **Cloud Networking Studio** on one EC2 host using [docker-compose.prod.yml](../docker-compose.prod.yml) (Postgres, API, static UI, Caddy). For environment variables and architecture, see [DEPLOYMENT.md](DEPLOYMENT.md).

**Assumptions:** You have an AWS account, a VPC with a public subnet (or private subnet + bastion), and an SSH key pair. Default path below uses **Amazon Linux 2023** and installs **Docker Engine** with the **Compose v2** plugin.

---

## 1. Launch an EC2 instance

### Console (quick path)

1. **EC2 → Launch instance**
2. **Name:** e.g. `cns-prod`
3. **AMI:** Amazon Linux 2023 (x86_64 or arm64 — match Docker install commands to your arch)
4. **Instance type:** `t3.small` or larger (API + Postgres + nginx + Caddy on one node)
5. **Key pair:** your SSH key
6. **Network:** VPC + subnet with a route to the internet (public IP or known private access)
7. **Security group (inbound):**
   - **TCP 22** — SSH (restrict to your IP)
   - **TCP 80** — HTTP to Caddy (restrict while testing; tighten for production)
8. **Storage:** **30 GiB** `gp3` or larger (Docker images + Postgres volume)
9. Launch

### AWS CLI (optional)

Replace placeholders (`YOUR_KEY`, `sg-…`, `subnet-…`). Resolve the latest AL2023 AMI for your region if you prefer a fixed `--image-id`.

```bash
export AWS_REGION="${AWS_REGION:-us-east-1}"
export KEY_NAME="YOUR_KEY"
export SG_ID="sg-xxxxxxxx"
export SUBNET_ID="subnet-xxxxxxxx"

aws ec2 run-instances \
  --region "$AWS_REGION" \
  --image-id "$(aws ssm get-parameters --region "$AWS_REGION" --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query 'Parameters[0].Value' --output text)" \
  --instance-type t3.small \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --subnet-id "$SUBNET_ID" \
  --associate-public-ip-address \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=cns-prod}]'
```

Note: Root device name can vary by AMI (`/dev/xvda` vs `/dev/sda1`). Adjust in the console if the CLI mapping fails.

---

## 2. SSH into the instance

```bash
ssh -i /path/to/YOUR_KEY.pem ec2-user@<PUBLIC_DNS_OR_IP>
```

Default user is **`ec2-user`** on Amazon Linux 2023. On **Ubuntu** AMIs, use **`ubuntu`**.

---

## 3. Install Docker Engine and Compose v2

### Amazon Linux 2023 (Docker CE from Docker’s repo)

```bash
sudo dnf -y update
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
# AL2023 does not match CentOS `$releasever` paths; pin to el9 for docker-ce packages:
sudo sed -i 's/\$releasever/9/g' /etc/yum.repos.d/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
```

Log out and SSH back in so the **`docker`** group applies:

```bash
exit
# from your laptop:
ssh -i /path/to/YOUR_KEY.pem ec2-user@<PUBLIC_DNS_OR_IP>
```

Verify:

```bash
docker version
docker compose version
```

### Ubuntu 22.04/24.04 (short path)

Follow [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) (official). Ensure the **`docker-compose-plugin`** package is installed so `docker compose` works.

---

## 4. Clone the repository

```bash
sudo mkdir -p /opt/cns
sudo chown "$USER:$USER" /opt/cns
cd /opt/cns
git clone https://github.com/<YOUR_ORG>/cloud-networking-studio.git
cd cloud-networking-studio
```

Use your real clone URL (HTTPS or SSH if the instance has a deploy key).

---

## 5. Create `.env` at the repo root

```bash
cp .env.example .env
nano .env   # or vim
```

**Minimum changes before exposing port 80 broadly:**

| Variable | Action |
|----------|--------|
| `POSTGRES_PASSWORD` | Set a strong secret |
| `DATABASE_URL` | Match `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` (default host name inside Compose is **`postgres`**) |
| `CNS_CORS_ORIGINS` | Include the **exact** browser origin users will type, e.g. `http://ec2-1-2-3-4.compute.amazonaws.com` or `http://YOUR_ELASTIC_IP` (scheme + host + port; no trailing slash) |

`VITE_API_BASE_URL=/api` is correct when the UI and API share the same host behind Caddy. Rebuild the **`frontend`** image only if you change it.

---

## 6. Validate Compose and start the stack

From the repository root (`/opt/cns/cloud-networking-studio`):

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml config --quiet   # optional: same check, no YAML dump
docker compose -f docker-compose.prod.yml up --build -d
./scripts/prod_smoke_test.sh
```

First boot builds images and waits on Postgres/backend health before starting Caddy.

---

## 7. Check logs

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=200 caddy backend postgres
```

Follow logs (Ctrl+C to stop):

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=100 backend frontend
```

Or use the helper (same idea, from your laptop or the instance after cloning):

```bash
./scripts/prod_logs.sh
```

---

## 8. Check health and smoke test

**Manual curls** (from the instance or anywhere that can reach port **80**):

```bash
export PUBLIC_URL="http://<EC2_PUBLIC_DNS_OR_IP>"
curl -sfI "$PUBLIC_URL/" | head -n 5
curl -sf "$PUBLIC_URL/api/health"
```

**Automated smoke** (defaults to `http://127.0.0.1` — fine on the instance itself):

```bash
./scripts/prod_smoke_test.sh
```

From your laptop against the public DNS:

```bash
CNS_BASE_URL="http://ec2-…compute.amazonaws.com" ./scripts/prod_smoke_test.sh
```

The same script always **creates a draft topology** and checks **GET /api/topologies**. To also run a **deploy + destroy** cycle against Docker (needs the backend socket mount), use:

```bash
CNS_BASE_URL="http://…" CNS_HEAVY_SMOKE=1 ./scripts/prod_smoke_test.sh
# or: ./scripts/prod_smoke_test.sh --heavy
```

Open in a browser: `http://<EC2_PUBLIC_DNS_OR_IP>/` — API docs: `/api/docs`.

---

## 9. Restart the stack safely

Recreate/update containers from the current compose file (keeps the named Postgres volume unless you use `down -v`):

```bash
cd /opt/cns/cloud-networking-studio
git pull
docker compose -f docker-compose.prod.yml up --build -d
```

Quick bounce **without** rebuilding images:

```bash
./scripts/prod_restart.sh
```

---

## 10. Stop and start

Stop containers (data volume **retained**):

```bash
docker compose -f docker-compose.prod.yml stop
```

Start again:

```bash
docker compose -f docker-compose.prod.yml start
```

Or `up -d` as in section 6.

---

## 11. Cleanup (remove containers and Postgres data)

**Destructive** — deletes the Compose project and the **`cns_pg_data`** volume:

```bash
cd /opt/cns/cloud-networking-studio
docker compose -f docker-compose.prod.yml down -v
```

Optional: remove the clone and free disk:

```bash
cd /opt/cns
rm -rf cloud-networking-studio
docker system prune -af   # only if you understand this removes unused images/containers
```

Terminate the instance from the **EC2 console** or:

```bash
aws ec2 terminate-instances --instance-ids i-xxxxxxxx
```

---

## 12. Real Docker workloads on the same EC2 host

To let the API create **real** containers on the Docker daemon, uncomment the **`/var/run/docker.sock`** bind mount under **`backend`** in `docker-compose.prod.yml`, then recreate:

```bash
docker compose -f docker-compose.prod.yml up -d --build backend
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for security implications.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `permission denied` on Docker socket | User in **`docker`** group; re-login after `usermod` |
| Port 80 in use | Set `CADDY_HTTP_PORT=8080` in `.env`, `up -d` again, open that port in the security group |
| Browser CORS errors | `CNS_CORS_ORIGINS` must match the site origin exactly |
| Backend unhealthy | `docker compose logs backend postgres` — wrong `DATABASE_URL` or Postgres not ready |
| Cannot reach instance | Security group, subnet routing, instance public IP |

---

## Related scripts (repository root)

| Script | Purpose |
|--------|---------|
| [scripts/prod_smoke_test.sh](../scripts/prod_smoke_test.sh) | HTTP checks, topology create/list, optional **heavy** deploy+destroy (`--heavy` / `CNS_HEAVY_SMOKE=1`) |
| [scripts/prod_logs.sh](../scripts/prod_logs.sh) | `compose ps` + tail backend/frontend logs |
| [scripts/prod_restart.sh](../scripts/prod_restart.sh) | Restart the prod compose services |

Local development and [scripts/demo_full_flow.sh](../scripts/demo_full_flow.sh) are unchanged; they target dev URLs and workflows, not this compose file.
