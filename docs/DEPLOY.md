# Deploying sitecheck to a VPS

This is the exact setup the live instance runs on: one small Linux VPS, Docker
Compose, Caddy for HTTPS, and GitHub Actions doing the deploys. Total cost is
a few euros a month for the server plus a domain.

```
GitHub push ──> CI (ruff, pytest, docker smoke test)
                 │ green
                 v
             Deploy workflow ──> build image ──> ghcr.io/aleksandersarkezi/sitecheck:sha-xxxxxxx
                 │
                 └── ssh ──> VPS: deploy.sh sha-xxxxxxx
                               ├─ docker compose pull + up -d
                               ├─ wait for /healthz
                               └─ unhealthy? roll back to the previous tag
```

## 1. Server

Any VPS with 1 vCPU / 1–2 GB RAM and Ubuntu 24.04 is enough (Hetzner CX22,
a small DigitalOcean droplet, etc.).

Log in as root once, create a normal user and lock SSH down:

```bash
adduser deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
```

In `/etc/ssh/sshd_config` set:

```
PermitRootLogin no
PasswordAuthentication no
```

then `systemctl restart ssh`. Keep your current session open and check that
`ssh deploy@SERVER_IP` works from a second terminal before you log out.

Firewall: only SSH, HTTP and HTTPS.

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw enable
```

Docker publishes ports through its own iptables rules and **ignores ufw** for
them. That's fine here because only Caddy publishes ports (80/443), but never
add `ports:` to the `app` service.

Automatic security updates:

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

## 2. Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

Log out and back in as `deploy` so the group change applies.

### Block the cloud metadata endpoint for containers

Most cloud providers (Hetzner included) expose instance metadata at
`169.254.169.254`. The app already refuses to connect there, but a second,
independent layer costs one line:

```bash
sudo iptables -I DOCKER-USER -d 169.254.169.254 -j DROP
sudo apt install -y iptables-persistent && sudo netfilter-persistent save
```

## 3. DNS

Create an `A` record (and `AAAA` if the server has IPv6) for the domain or
subdomain you want, e.g. `sitecheck.yourdomain.si`, pointing to the server IP.
Wait until `dig +short sitecheck.yourdomain.si` returns the IP. Caddy can only
get a certificate once DNS points at the server.

## 4. Stack files on the server

As `deploy`:

```bash
mkdir -p ~/sitecheck && cd ~/sitecheck
```

Copy `deploy/docker-compose.yml`, `deploy/Caddyfile`, `deploy/deploy.sh`,
`deploy/.env.example` and `deploy/sites.example.txt` from the repo into this
folder (the deploy workflow keeps the first three up to date afterwards), then:

```bash
cp .env.example .env
nano .env                 # SITE_DOMAIN, ACME_EMAIL, SITECHECK_WEBHOOK_URL
chmod 600 .env
cp sites.example.txt sites.txt
nano sites.txt            # sites you own or may check
```

## 5. Make the image pullable

After the first successful Deploy run, the image exists at
`ghcr.io/aleksandersarkezi/sitecheck`. On GitHub: your profile → Packages →
sitecheck → Package settings → Change visibility → Public. (Alternatively keep
it private and run `docker login ghcr.io` on the server with a read-only
token.)

## 6. GitHub secrets

Create a key pair used only for deploys, on your own computer:

```bash
ssh-keygen -t ed25519 -f sitecheck_deploy -N "" -C "github-actions-deploy"
ssh-copy-id -i sitecheck_deploy.pub deploy@SERVER_IP
ssh-keyscan -t ed25519 SERVER_IP
```

Repo → Settings → Environments → New environment `production`, then add these
environment secrets:

| Secret | Value |
| --- | --- |
| `VPS_HOST` | server IP or hostname |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | contents of `sitecheck_deploy` (the private key) |
| `VPS_KNOWN_HOSTS` | the output of the `ssh-keyscan` line |

Pinning the host key means a deploy will refuse to talk to a server that isn't
yours, instead of trusting whatever answers on first connect.

Delete `sitecheck_deploy` from your computer afterwards, or keep it in a
password manager.

## 7. First deploy

Push to `main`, or Actions → Deploy → Run workflow. Watch the run; when it's
green, open `https://sitecheck.yourdomain.si`.

Check it with itself:

```bash
sitecheck sitecheck.yourdomain.si
```

It should get an A.

## Day-to-day

```bash
cd ~/sitecheck
docker compose ps                     # status + health
docker compose logs -f app            # web logs
docker compose logs -f monitor        # monitor runs and alerts
docker compose logs -f caddy          # access logs, certificate renewals
bash deploy.sh sha-1a2b3c4            # roll back to an older build
docker compose exec monitor sitecheck-monitor --watchlist /config/sites.txt --db /data/sitecheck.db
                                      # force a monitor run now
```

Metrics are available only from the server itself:

```bash
docker compose exec app python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())"
```

### Backups

All state is one SQLite file in the `app_data` volume:

```bash
docker compose exec app python -c "import sqlite3;s=sqlite3.connect('/data/sitecheck.db');d=sqlite3.connect('/data/backup.db');s.backup(d)"
docker compose cp app:/data/backup.db ./backup-$(date +%F).db
```

Caddy's certificates live in the `caddy_data` volume. Don't delete it, or
Caddy has to request new certificates and can hit Let's Encrypt rate limits.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Caddy logs `no such host` / certificate errors | DNS doesn't point at the server yet, or port 80 is blocked. |
| Deploy job says "secrets not configured" | Secrets were added to the repo instead of the `production` environment, or names don't match. |
| `docker compose pull` → `denied` | The GHCR package is still private (step 5). |
| Deploy rolls back | Look at the `app` logs printed in the job output. |
| Caddy won't start with `permission denied` binding :80 | Remove the `cap_drop`/`cap_add` lines from the `caddy` service; some Docker setups need the image's default capabilities. |
