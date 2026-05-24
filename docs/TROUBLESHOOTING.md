# Troubleshooting

Common deployment and EC2 bootstrap failures.

## Cloud-init Docker install: malformed `docker.list`

### Symptom

Cloud-init ends with `status: error`. `/var/log/cloud-init-output.log` shows:

```text
E: Malformed entry 1 in list file /etc/apt/sources.list.d/docker.list ([option] not assignment)
FATAL: Docker verification failed after install
```

GitHub Actions SSH bootstrap may also fail with `Docker not available after 300s`.

### Cause

An invalid **`/etc/apt/sources.list.d/docker.list`** line was written during EC2 **user_data** (Terraform `infra/terraform/templates/user_data.sh.tpl`) or a one-off manual edit. Apt requires bracket options like:

```text
deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable
```

Common mistakes:

- `signed-by` without `=` and a path (`signed-by=/etc/apt/keyrings/docker.asc`)
- Single-line echo that drops the codename or breaks bracket syntax
- Stale malformed file left from a previous boot attempt
- Using `$(. /etc/os-release && echo "$VERSION_CODENAME")` under `set -u` inside Terraform user_data — can fail with `VERSION_CODENAME: unbound variable`. Source `/etc/os-release` first, set `UBUNTU_CODENAME="${VERSION_CODENAME:-noble}"`, then write `docker.list`.

### Fix (in repo)

The bootstrap scripts now:

1. `rm -f /etc/apt/sources.list.d/docker.list` before writing
2. Download **`/etc/apt/keyrings/docker.asc`** (official Docker apt key format for Ubuntu 24.04 noble)
3. Write the multi-line `deb [arch=… signed-by=…]` entry with `$(. /etc/os-release && echo "$VERSION_CODENAME")`
4. `cat /etc/apt/sources.list.d/docker.list` for cloud-init logs
5. On failure, print `docker.list`, `ls -la /etc/apt/keyrings`, and `tail /var/log/cloud-init-output.log`

Files:

- `infra/terraform/templates/user_data.sh.tpl` — first-boot cloud-init
- `scripts/ec2_bootstrap_docker.sh` — SSH deploy bootstrap (ephemeral, staging, production)

### Fix (existing instance)

SSH to the instance and repair the repo file, or terminate the instance and re-run Terraform / **Deploy staging** so a fresh user_data run applies (user_data only runs on first boot — for a broken instance, prefer **replace** the EC2 instance or run `scripts/ec2_bootstrap_docker.sh` manually):

```bash
sudo rm -f /etc/apt/sources.list.d/docker.list
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
UBUNTU_CODENAME="${VERSION_CODENAME:-noble}"
ARCH="$(dpkg --print-architecture)"
echo "ARCH=${ARCH}"
echo "UBUNTU_CODENAME=${UBUNTU_CODENAME}"
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "${ARCH}" "${UBUNTU_CODENAME}" \
  | sudo tee /etc/apt/sources.list.d/docker.list
grep -Eq '^deb \[arch=(amd64|arm64) signed-by=/etc/apt/keyrings/docker.asc\] https://download.docker.com/linux/ubuntu (noble|jammy|focal) stable$' /etc/apt/sources.list.d/docker.list
cat /etc/apt/sources.list.d/docker.list
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker --version
docker compose version
systemctl is-active docker
```

### Related docs

- [STAGING_DEPLOYMENT.md](./STAGING_DEPLOYMENT.md)
- [EPHEMERAL_CI_ENVIRONMENTS.md](./EPHEMERAL_CI_ENVIRONMENTS.md)
- [EC2_RUNBOOK.md](./EC2_RUNBOOK.md)
