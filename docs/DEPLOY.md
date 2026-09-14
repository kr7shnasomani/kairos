# Deploying the Kairos backend on AWS

This guide hosts **everything except the frontend** on one EC2 instance in **Mumbai (`ap-south-1`)**, so
the public can use Kairos. The frontend is deployed separately on Vercel and calls this server over HTTPS.

```
Browser ──► https://kairos-deterium.vercel.app          Vercel: Next.js frontend
   │
   └──────► https://kairos-deterium.duckdns.org          EC2: Caddy :443 ──► FastAPI :8000
                 ├─ Celery · Temporal + Postgres · Temporal activity and elicitation workers · Go connector
                 ├─ Elasticsearch · Redis · OPA                    (local to the host, never exposed)
                 └─ Supabase · Neo4j Aura · Qdrant Cloud · Grafana Cloud · NVIDIA NIM · Jina · Groq   (cloud)
```

This guide uses the project's DuckDNS name, `kairos-deterium.duckdns.org`. If you use a different name, replace it everywhere below.

**Files this guide uses (all in this repository):**

| File | Purpose |
|---|---|
| [`docker-compose.yml`](../docker-compose.yml) | The stack. The `kairos-caddy` service (profile `prod`) is the HTTPS front for the API and only runs on the server. |
| [`infra/caddy/Caddyfile`](../infra/caddy/Caddyfile) | Caddy config: automatic HTTPS, proxies to `kairos-backend-api:8000` |
| [`db/snapshots/kairos-es-data.tar.gz`](../db/snapshots/) | Snapshot of the local Elasticsearch index for the golden dataset |

`docker-compose.override.yml` is for **local development only**. It is never copied to or used on the server.

## Current deployment (15 September 2026)

| | |
|---|---|
| Frontend | **https://kairos-deterium.vercel.app** · Vercel project `kairos` (team `kr1shnasomani-preview`), root `frontend`, Vercel Authentication **off** |
| API | **https://kairos-deterium.duckdns.org** (`/health`, `/docs`) |
| Server | EC2 `i-012800d81f549557b` · `m7i-flex.large` · Ubuntu 24.04 · 30 GB gp3 · Mumbai `ap-south-1` |
| Address | Elastic IP `3.7.186.159` ← DuckDNS `kairos-deterium` |
| Security group | 22 (your IP), 80, 443 |
| Certificate | Let's Encrypt, renewed automatically by Caddy |
| Running | the 11 services started by `make prod`; memory about 2.8 GiB of 7.6 GiB |
| Account | AWS Free plan, $100 credit, about $2.63 a day while running |

**Accepted risk:** the login page's "Try demo · signs in as admin" button, and the seeded passwords in the
repository, let anyone act as admin on the live data. Replace them with a read-only demo account before
wider sharing.

---

## Contents

1. [Concepts in one minute](#1-concepts-in-one-minute)
2. [Sizing and cost](#2-sizing-and-cost)
3. [Before you start](#3-before-you-start)
4. [Stop surprise charges](#4-stop-surprise-charges)
5. [Get an HTTPS name with DuckDNS](#5-get-an-https-name-with-duckdns)
6. [Launch the EC2 instance](#6-launch-the-ec2-instance)
7. [Prepare the server](#7-prepare-the-server)
8. [Copy the code and secrets](#8-copy-the-code-and-secrets)
9. [Production `.env`](#9-production-env)
10. [Start the backend](#10-start-the-backend)
11. [Verify](#11-verify)
12. [Connect the Vercel frontend](#12-connect-the-vercel-frontend)
13. [Never run on the server](#13-never-run-on-the-server)
14. [Operate: update, logs, stop, tear down](#14-operate-update-logs-stop-tear-down)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Concepts in one minute

| Piece | What it does |
|---|---|
| **EC2 instance** | The virtual server that runs the Docker stack |
| **Elastic IP** | A fixed public IP, so the address survives a stop and start |
| **DuckDNS** | A free domain name (`kairos-deterium.duckdns.org`) that points at the Elastic IP |
| **Caddy** | A small web server on the instance. It gets a free Let's Encrypt certificate and forwards HTTPS traffic to FastAPI. |
| **Vercel** | Hosts the Next.js frontend. Browsers block an HTTPS page from calling a plain-HTTP API, which is why the API needs Caddy and a domain. |

**Why Elasticsearch stays on the same host.** Measured without the frontend, Elasticsearch uses 1.09 GiB
(1 GiB heap, 133 MB in use) and holds about 140 KB of data. It fits comfortably on an 8 GiB host.

Hosting it elsewhere would cost more and add a network hop to every search, because Elastic Cloud has no
free tier. Leaving it out is possible: the backend starts without it, and search falls back to Qdrant and
the graph. But that loses four things:

- exact tag and part-number matches
- asset search
- the Elasticsearch indexing step of document ingestion
- the conditions under which the benchmark figures were measured

---

## 2. Sizing and cost

Prices are AWS on-demand rates for **Asia Pacific (Mumbai)**, checked on 14 September 2026. A month is 730 hours.

| Item | Rate | t4g.large (Paid plan) | m7i-flex.large (Free plan) |
|---|---|---|---|
| Instance, 2 vCPU / 8 GiB | per hour | $0.0448 → **$32.70/mo** | $0.10075 → **$73.55/mo** |
| 30 GB gp3 disk | $0.0912 / GB-month | $2.74/mo | $2.74/mo |
| 1 public IPv4 (Elastic IP) | $0.005 / hour | $3.65/mo | $3.65/mo |
| **Total** | | **$39.09/mo · $1.29/day** | **$79.94/mo · $2.63/day** |
| Days $100 of credit lasts | | about 77 | about 38 |

**Other costs:**
- **Data transfer out:** the first 100 GB per month is free, and API responses are kilobytes.
- **Model calls** (NVIDIA NIM, Jina, Groq) are billed by those providers, not AWS.

**Memory, measured without the frontend:**

| Service | Memory |
|---|---|
| API | 286 MiB |
| Celery | 632 MiB |
| Temporal activity worker | 41 MiB |
| Elicitation worker | 100 MiB |
| Go connector | 48 MiB |
| Elasticsearch | 1.09 GiB |
| Redis | 12 MiB |
| Temporal | 144 MiB |
| Temporal Postgres | 54 MiB |
| OPA | 25 MiB |
| **Total** | **about 2.4 GiB** |

- **Realistic peak: about 5 GiB.** That assumes Elasticsearch reaches its 2 GiB container limit, Celery grows
  under load, and the OS takes about 0.6 GiB. An 8 GiB host with 2 GiB of swap has headroom.
- **Don't use a 4 GiB host** (such as c7i-flex.large). It starts at about 3 GiB used, with no room for
  Elasticsearch to grow.
- **CPU:** the idle stack uses about 4% of 2 vCPUs, well under the 30% baseline of a t4g.large.

---

## 3. Before you start

**Pick the instance by account plan.** Check which plan you're on at
**https://console.aws.amazon.com/billing/home#/freetier**.

- **Free plan → `m7i-flex.large` (x86_64).**
  - Free-plan accounts can launch only these types: `t3.micro`, `t3.small`, `t4g.micro`, `t4g.small`,
    `c7i-flex.large` and `m7i-flex.large`. Of those, only `m7i-flex.large` has 8 GiB.
  - The Free plan cannot charge your card.
  - The account closes when credits run out or after 6 months, unless you upgrade.
- **Paid plan → `t4g.large` (Graviton, arm64).** It costs half as much.
  - Credits pay for it, but once they run out your card is charged. The budget in section 4 is the guard.
  - Every image in the stack publishes an arm64 build, and the backend and connector images build on arm64.

**Check your credits and their expiry dates** at **https://console.aws.amazon.com/billing/home#/credits**.

**You need:**
- An AWS account with credits
- A GitHub account (to sign in to DuckDNS)
- A Vercel account (for the frontend)
- This repository with a working `.env` on your Mac

**Decide before going public: the demo login.** The login page has a
**"Try demo · signs in as admin"** button.

- **The risk:** on a public deployment, any visitor becomes admin. They can sign permits, promote quarantined
  items and supersede documents in the real Supabase, Neo4j Aura and Qdrant data, and that data has no backup.
- **Recommended:** point the button at a read-mostly persona, and share admin credentials privately.

---

## 4. Stop surprise charges

Do this before launching anything. Go to **https://console.aws.amazon.com/costmanagement/home#/budgets**.

In **Advanced options → Charge types**, a ticked **Credits** box means credits are subtracted, so the budget
tracks what you would actually pay. Unticking it tracks usage before credits, which is how fast credits burn.

**Budget 1: credit burn (everyone).**

1. Choose **Create budget**, then **Customize (advanced)**, then **Cost budget**.
2. Set the details:
   - **Name:** `credit-burn-50usd`
   - **Period:** Monthly
   - **Budget renewal type:** Recurring
   - **Budgeting method:** Fixed
   - **Amount:** `50.00`
3. Under **Budget scope**, keep **All AWS services**, open **Advanced options** and **untick Credits**.
4. Add email alerts at **Actual 80%** and **Forecasted 100%**.

**Budget 2: real charges reach $1 (Paid plan only).**

Skip this on the Free plan, which cannot charge your card. On the Paid plan, create a second cost budget named
`real-charges-1usd`: monthly, amount `1.00`, **leave Credits ticked**, alerts at **Actual 50%** and **Actual 100%**.

The first two budgets on an account are free.

---

## 5. Get an HTTPS name with DuckDNS

1. Open **https://www.duckdns.org** and sign in with GitHub.
2. Under **sub domain**, enter a name (this project uses `kairos-deterium`) and click **add domain**.
3. Leave **current ip** empty for now. You fill it in during step 6.

**Why not a Cloudflare quick tunnel?** Quick tunnels do not support Server-Sent Events, so the Copilot answer
stream would break. DuckDNS with Caddy is free, needs no purchased domain, and supports streaming.

---

## 6. Launch the EC2 instance

Open **https://ap-south-1.console.aws.amazon.com/ec2/home?region=ap-south-1#LaunchInstances:**. Confirm the
region at the top right reads **Asia Pacific (Mumbai)**.

| Field | Value |
|---|---|
| Name | `kairos-backend` |
| AMI | **Ubuntu Server 24.04 LTS**: **64-bit (Arm)** for t4g.large, **64-bit (x86)** for m7i-flex.large |
| Instance type | `t4g.large` (Paid plan) or `m7i-flex.large` (Free plan) |
| Key pair | **Create new key pair**: name `kairos-aws`, type ED25519, format `.pem` |
| Network settings → Edit | Auto-assign public IP: **Enable** |
| Security group | Create `kairos-backend-sg` with the rules below |
| Configure storage | **30 GiB**, **gp3** |
| Advanced details → Credit specification (t4g only) | Leave **Unlimited** for the first build; switch it in [section 10](#10-start-the-backend) |

**Security group inbound rules.** Add nothing else. Never open 8000, 9200, 6379, 7233 or 8181.

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **My IP** | Your access only |
| HTTP | 80 | `0.0.0.0/0` | Let's Encrypt validation, then a redirect to HTTPS |
| HTTPS | 443 | `0.0.0.0/0` | The API |

Launch the instance, then:

1. **Allocate a fixed IP.**
   - Open **https://ap-south-1.console.aws.amazon.com/ec2/home?region=ap-south-1#Addresses:**.
   - Click **Allocate Elastic IP address**, then **Allocate**.
   - Choose **Actions → Associate Elastic IP address**, pick instance `kairos-backend`, and associate.
2. **Point DuckDNS at it.** On DuckDNS, paste the Elastic IP into **current ip** and click **update ip**.
3. **Store the key on your Mac:**

```bash
mv ~/Downloads/kairos-aws.pem ~/.ssh/ && chmod 400 ~/.ssh/kairos-aws.pem
```

4. **Confirm the name resolves.** This must print the Elastic IP:

```bash
dig +short kairos-deterium.duckdns.org
```

5. **Connect:**

```bash
ssh -i ~/.ssh/kairos-aws.pem ubuntu@kairos-deterium.duckdns.org
```

---

## 7. Prepare the server

Run on the server:

```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y make                         # needed for `make prod`
curl -fsSL https://get.docker.com | sudo sh          # Docker's official install script (Engine + Compose v2)
sudo usermod -aG docker ubuntu

# 2 GiB swap as a safety net
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Elasticsearch memory-map limit, and keep it out of swap
printf 'vm.max_map_count=262144\nvm.swappiness=10\n' | sudo tee /etc/sysctl.d/99-kairos.conf
sudo sysctl --system

exit   # log out and back in so the docker group applies
```

**Why `vm.max_map_count`.**
- Ubuntu defaults to 65,530, and Elasticsearch asks for 262,144.
- With `discovery.type: single-node`, Elasticsearch treats the node as development mode, so the failed check is
  only logged and it still starts.
- It can still fail later under load when it runs out of memory maps. Setting the value costs nothing.

---

## 8. Copy the code and secrets

Run on your Mac. This copies the repository without the frontend, git history, the dev override or local
tooling folders. It goes over SSH, so no GitHub token is needed.

**First time only** (copies your `.env` too, which section 9 then switches to production):

```bash
rsync -az --delete --exclude '.git' --exclude 'frontend' --exclude 'node_modules' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude '.claude' --exclude '.agents' --exclude 'supabase/.temp' --exclude 'docker-compose.override.yml' -e "ssh -i ~/.ssh/kairos-aws.pem" /Users/apple/Documents/Projects/kairos/ ubuntu@kairos-deterium.duckdns.org:~/kairos/
```

**Every update after that** (never touches the server's `.env` or its backups):

```bash
rsync -az --delete --exclude '.git' --exclude 'frontend' --exclude 'node_modules' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude '.claude' --exclude '.agents' --exclude 'supabase/.temp' --exclude 'docker-compose.override.yml' --exclude '.env' --exclude '.env.bak.*' -e "ssh -i ~/.ssh/kairos-aws.pem" /Users/apple/Documents/Projects/kairos/ ubuntu@kairos-deterium.duckdns.org:~/kairos/
```

**About `.env`:**
- The first-time copy sends your development `.env`; the update copy excludes it. Re-running the first-time
  command on a live server would replace its production settings with your development ones.
- It holds cloud credentials, so it lives only on your Mac and this server.
- It is listed in `.gitignore`. Never commit it.

---

## 9. Production `.env`

On the server:

```bash
cd ~/kairos
openssl rand -hex 32   # run twice: one value for APP_SECRET_KEY, one for INTERNAL_API_KEY
nano .env
```

Set or add these lines:

```
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=<first random value>
INTERNAL_API_KEY=<second random value>
CORS_ORIGINS=["http://localhost:3000"]
RATE_LIMIT_PER_MINUTE=600
KAIROS_DOMAIN=kairos-deterium.duckdns.org
```

| Setting | Why |
|---|---|
| `APP_ENV=production` | Turns on the production guardrails in `api/config.py`. The API refuses to start with a default `INTERNAL_API_KEY` or `APP_SECRET_KEY`, or an empty `SUPABASE_JWT_SECRET`. |
| `INTERNAL_API_KEY` | The default value grants admin. The Go connector reads the same `.env`, so it picks up the new key. |
| `CORS_ORIGINS` | A placeholder until section 12. It must be a JSON list. |
| `RATE_LIMIT_PER_MINUTE=600` | The limit is enforced only in production and applies per client IP. Vercel server-side renders reach the API from a few shared IPs, so the default 120 is too tight. 600 still stops a script from draining model quotas. |
| `KAIROS_DOMAIN` | Read by the `kairos-caddy` service for the certificate |

Leave every other value unchanged.

---

## 10. Start the backend

On the server:

**On a fresh server, restore the search index first.** A new Elasticsearch volume is empty, so asset search
and exact-match retrieval return nothing without the snapshot. Restoring before the first start means
Elasticsearch never needs a restart. This writes only to this server's local Elasticsearch, never to
Supabase, Neo4j or Qdrant.

```bash
cd ~/kairos
docker volume create --label com.docker.compose.project=kairos --label com.docker.compose.volume=kairos-elasticsearch_data kairos_kairos-elasticsearch_data
docker run --rm -v kairos_kairos-elasticsearch_data:/data -v "$PWD/db/snapshots":/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/kairos-es-data.tar.gz -C /data && chown -R 1000:0 /data"
```

**Then build and start everything:**

```bash
cd ~/kairos && make prod
```

`make prod` builds the backend and connector images, then starts the 11 backend services and `kairos-caddy`.
It is the same as:

```bash
docker compose -f docker-compose.yml --profile prod build kairos-backend-api kairos-backend-go
docker compose -f docker-compose.yml --profile prod up -d kairos-elasticsearch kairos-redis kairos-opa kairos-temporal-postgres kairos-temporal kairos-backend-api kairos-celery-worker kairos-temporal-activity-worker kairos-elicitation-worker kairos-backend-go kairos-caddy
```

- **Always use `make prod`, or pass `-f docker-compose.yml --profile prod` and name the services.**
  - A plain `docker compose up` loads the dev override, which publishes Elasticsearch, Redis and Temporal ports.
  - A bare `up` or `build` also tries to build the frontend, which is not on the server.
- **The first build took about 3 minutes** on the m7i-flex.large.

To restore the snapshot on a server that is already running, stop Elasticsearch first
(`docker compose -f docker-compose.yml --profile prod stop kairos-elasticsearch`), run the `docker run` line
above, then `make prod`.

**t4g.large only, after the build:**
1. In EC2, select the instance and choose **Actions → Instance settings → Change credit specification**.
2. Untick **Unlimited** and save.

The idle stack sits far below the 30% CPU baseline, so this removes a possible extra charge without slowing anything.

---

## 11. Verify

On the server:

```bash
docker compose -f docker-compose.yml --profile prod ps
free -h
```

- Every service should report `healthy` or `running`.
- `free -h` should show about 2.5 to 3 GiB used.

From your Mac:

```bash
curl -s https://kairos-deterium.duckdns.org/health
```

It should return JSON over a valid certificate.

In a browser, open **https://kairos-deterium.duckdns.org/docs**. You should see Swagger UI with a padlock in the address bar.

---

## 12. Connect the Vercel frontend

The Vercel project `kairos` already exists and is linked to `kr7shnasomani/kairos` with **Root Directory**
`frontend`; every push to `main` deploys. For a new project, import the repository at
**https://vercel.com/new** and set the root directory to `frontend`.

**1. Environment variables (Production):**

| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://kairos-deterium.duckdns.org` |
| `API_INTERNAL_URL` | `https://kairos-deterium.duckdns.org` |
| `NEXT_PUBLIC_AUTH_STRICT` | `true` |

Set them in **Settings → Environment Variables**, or from `frontend/` with the Vercel CLI:

```bash
export VERCEL_ORG_ID=team_CV55a739gesEJLo0ydqxhrwZ VERCEL_PROJECT_ID=prj_4XwxHOCZDI4Ioir6XEj4pubr3zhC
printf '%s' 'https://kairos-deterium.duckdns.org' | vercel env add NEXT_PUBLIC_API_URL production
printf '%s' 'https://kairos-deterium.duckdns.org' | vercel env add API_INTERNAL_URL production
printf '%s' 'true' | vercel env add NEXT_PUBLIC_AUTH_STRICT production
```

**2. Rebuild.** `NEXT_PUBLIC_*` values are baked in at build time, so changing them needs a new build: in the
dashboard, **Deployments → ⋯ → Redeploy**, or `vercel redeploy <deployment-url> --target production`.
Without them the build silently falls back to `http://localhost:8000`.

**3. Allow the frontend origin on the server** and recreate the API:

```bash
cd ~/kairos && sed -i 's#^CORS_ORIGINS=.*#CORS_ORIGINS=["https://kairos-deterium.vercel.app"]#' .env
docker compose -f docker-compose.yml --profile prod up -d --force-recreate kairos-backend-api
```

If you add a custom domain on Vercel, add it to the same JSON list.

**4. Public access.** Vercel Authentication is on by default, so visitors who are not signed in to your Vercel
team see a login screen. For a public site, go to **Settings → Deployment Protection → Vercel Authentication**
and choose **Only Preview Deployments** (production public, previews private). The CLI command
`vercel project protection disable kairos --sso` turns it off for previews as well; that is how it is set now.

---

## 13. Never run on the server

The server is connected to the **real cloud stores that hold the golden dataset**. These write to them or delete
from them (see the 🛑 rule in `CLAUDE.md`):

- `make seed`, `make load-dataset`, `make init-all`, `make purge-test-data`, `make nuke`
- the write scripts in `backend/scripts/`
- the full `pytest tests/` suite, whose session teardown purges cloud data

---

## 14. Operate: update, logs, stop, tear down

**Update the code.** Run the **update** rsync from section 8 (the one that excludes `.env`), then on the server:

```bash
cd ~/kairos && make prod
```

**Logs:**

```bash
docker compose -f docker-compose.yml --profile prod logs -f --tail 100 kairos-backend-api
```

### Pause between events (stop and start)

**Stop:** EC2 → Instances → select `kairos-backend` → **Instance state → Stop instance**.

- **What keeps billing while stopped:** the disk ($2.74/mo) and the Elastic IP ($3.65/mo), about
  **$6.40 a month, or $0.21 a day**. The instance charge ($2.42 a day) stops.
- **What survives:** the disk, the code, `.env`, the Elasticsearch index, the certificate, and the address.
  DuckDNS and the Vercel frontend need no changes.
- **While it is stopped** the Vercel site still loads, but every page shows "backend unreachable".

**Start:** **Instance state → Start instance**, wait about 2 minutes, then check:

```bash
curl -s https://kairos-deterium.duckdns.org/health/
```

Docker starts at boot and every container restarts on its own (`restart: unless-stopped`), so nothing needs
to be run. If SSH is refused, your home IP has probably changed: edit the security group's SSH rule and choose
**My IP** again.

**Before starting again after a long pause, check:**

1. **AWS plan window.** The Free plan ends 6 months after the account was created, or when the credit runs out,
   whichever comes first. Check the date on the Billing home page.
2. **Supabase.** Free projects pause after a period of inactivity. If it shows as paused, restore it from the
   Supabase dashboard before starting the server.
3. **Neo4j Aura.** Free instances pause after 3 days idle; `.github/workflows/uptime.yml` queries it daily.
   GitHub disables scheduled workflows after 60 days without repository activity, so re-enable it from the
   Actions tab if needed.
4. **Qdrant Cloud.** Confirm the cluster is running in the Qdrant console.

**Cheaper for long gaps:** create a snapshot of the volume, terminate the instance and release the Elastic IP.
The snapshot bills only the used data (about 11 GB), well under $1 a month. Restoring means launching a new
instance from that snapshot, attaching a new Elastic IP, and updating DuckDNS with the new address.

**Tear down to $0:**
1. Terminate the instance.
2. Release the Elastic IP.
3. Confirm **https://ap-south-1.console.aws.amazon.com/ec2/home?region=ap-south-1#Volumes:** is empty.
4. Check **https://console.aws.amazon.com/ec2globalview/home** for leftovers in other regions.

---

## 15. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| API container exits at start with a settings error | Production guardrail. Set a non-default `APP_SECRET_KEY` and `INTERNAL_API_KEY`, and a non-empty `SUPABASE_JWT_SECRET`. |
| `https://…/health` fails, but `curl localhost:8000/health` works on the server | Ports 80 or 443 are not open in the security group, or DuckDNS does not point at the Elastic IP (`dig +short`). Check `docker logs kairos-caddy` for certificate errors. |
| Browser shows a CORS error from the Vercel site | The Vercel origin is missing from `CORS_ORIGINS`, or the API was not recreated after editing `.env`. |
| Asset search and exact-match results are empty | The Elasticsearch snapshot was not restored (section 10). |
| Elasticsearch restarts or is killed | Check `free -h` and `dmesg | tail`. Confirm swap is on and `vm.max_map_count` is 262144. |
| Copilot answers arrive all at once instead of streaming | Something is buffering Server-Sent Events. Keep `infra/caddy/Caddyfile` without an `encode` block. |
| Many `429` responses during a demo | Raise `RATE_LIMIT_PER_MINUTE` in `.env`, then recreate `kairos-backend-api`. |
