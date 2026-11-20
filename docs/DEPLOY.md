# Deploy AttendFlow with employee sessions

Use a disposable PostgreSQL database and the synthetic CSVs for demos. Employees
sign in with their email and the password supplied by the operator. The database
determines each employee's role. Session-mode API requests ignore `X-Actor-Id`.
`/healthz`, the sign-in page, and its frontend assets are public. The API docs
and schema URLs are disabled in session mode.

## Hosting options

**Target: a single-node k3s cluster on one AWS VM** (Phase 22). See
[Kubernetes on k3s](#kubernetes-on-k3s-the-deployment-target). The Render and Koyeb/Neon
setups below stay as optional alternatives and are not used.

Free-tier details checked 20 November 2026.

| Rank | Setup | Limits |
| --- | --- | --- |
| 1 | Render Free Web Service + Render Free Postgres | One HTTPS URL, Git deployment, managed Postgres on the private network. Web sleeps after 15 idle minutes and takes about a minute to wake. 750 running instance-hours and 500 build minutes per workspace per month. Free database has 1 GB and expires after 30 days. [Free tier](https://render.com/docs/free), [build limits](https://render.com/docs/build-pipeline), [database limits](https://render.com/articles/from-side-project-to-production-scaling-your-first-app). |
| 2 | Koyeb Free Web Service + Neon Free Postgres | One HTTPS URL and an extra provider plus registry. Koyeb sleeps after one idle hour and requires card verification. Using a prebuilt image consumes no Koyeb build minutes. Neon has 1 GB and 100 compute-unit hours per project per month, sleeps after five idle minutes, and lists no fixed project expiry in its free-plan limits. Its free compute allowance can be exhausted while the app keeps querying it. [Koyeb plan](https://www.koyeb.com/docs/faqs/pricing), [idle behavior](https://www.koyeb.com/docs/run-and-scale/scale-to-zero), [image hosting](https://www.koyeb.com/docs/build-and-deploy/prebuilt-docker-images), [Neon limits](https://neon.com/faqs/free-plan-limits-and-quotas). |

The scheduler runs in the API process and pauses when the web service sleeps.
Use one replica and one Uvicorn worker. Before any environment change or manual
redeploy, stop the old scheduler and wait for `cycle_in_progress=false`. This avoids
running schedulers in two processes during a rollout. Once the new instance starts,
`SCHEDULER_ENABLED=true` starts its timer again. A manual model-free cycle works once
the service wakes. The free filesystem is temporary, so durable application state belongs
in PostgreSQL.

## Settings profiles

Use **Locked** for the first deployment and baseline smoke test. Both profiles
use employee sessions, same-origin URLs, and synthetic data. Keep diagnostics
off. Generate a separate strong demo password and session signing secret.

| Setting | Locked | Guided demo |
| --- | --- | --- |
| `ATTENDFLOW_ENABLE_SEED` | `false` | `false` |
| `ATTENDFLOW_DEMO_MODE` | `false` | `true` |
| `ATTENDFLOW_DEMO_RESET_ENABLED` | `false` | `true` |
| `ATTENDFLOW_DEMO_EXTRA_WEEK` | `false` | `true` |
| `DEVICE_API_KEY` | Unset | Unset |

Guided mode enables the simulator, demo clock, admin reset and email-fill buttons
for Amit, Ravi, and Priya. Reset recreates all demo credentials from the configured
password and revokes existing sessions. Sign in again after a reset. After reset, the
extra week is available for the payroll sign-off demo. Moving the workflow clock
leaves the attendance cutoff fixed. Locked mode alone does not undo any simulated
changes or delete previously seeded synthetic records.

### Runtime and build variables

| Variable | Deployed value or default | Secret? |
| --- | --- | --- |
| `DATABASE_URL` | Required runtime URL. Use Render's internal URL or Neon's direct URL including `sslmode=require`. Both `postgres://` and `postgresql://` normalize to `postgresql+psycopg://`. | Yes |
| `ATTENDFLOW_DEPLOYED` | `true`, enforced by the container launcher. | No |
| `ATTENDFLOW_AUTH_MODE` | `session`. Local development defaults to `header`. An explicit deployed `header` configuration retains the legacy Basic Auth gate. | No |
| `ATTENDFLOW_SESSION_SECRET` | Required in deployed and session modes, at least 32 bytes. Generate independently with `openssl rand -hex 32`. Changing it invalidates existing cookies. | Yes |
| `ATTENDFLOW_DEMO_PASSWORD` | Required for deployed demo seeding and reset. Generate with `openssl rand -hex 24`. | Yes |
| `ATTENDFLOW_COOKIE_SECURE` | `true` for a public HTTPS URL. For loopback HTTP development only, set `false`. | No |
| `ATTENDFLOW_TRUSTED_PROXY` | `false` by default. Set `true` for a single trusted Traefik hop with direct client access to the app blocked. | No |
| `PORT` | Provider-assigned HTTP port, default `10000`. Published HTTPS is terminated by the provider. | No |
| `ATTENDFLOW_ENABLE_SEED`, `ATTENDFLOW_DEMO_MODE`, `ATTENDFLOW_DEMO_RESET_ENABLED`, `ATTENDFLOW_DEMO_EXTRA_WEEK` | Use the profile above. Reset wipes the DB. Enable API seed only when provisioning a disposable synthetic DB. | No |
| `DEVICE_API_KEY` | Leave unset in both profiles. To enable external punch ingestion deliberately, use a separate random value sent in `X-Device-Key`. | Yes, if used |
| `DEVICE_MAX_BACKDATE_DAYS` | `7`. | No |
| `ATTENDFLOW_AS_OF` | `2026-04-16T08:00:00` (local wall time without offset). Preserves the fixtures. | No |
| `ATTENDFLOW_DATA_DIR` | Unset. The image contains the synthetic `/app/data`. | No |
| `ATTENDFLOW_CORS_ORIGINS` | Unset for same origin. Any supplied entries must be exact HTTPS origins. | No |
| `SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_SECONDS` | `false`, `60` on k3s at first (see [turn the scheduler on](#9-later-turn-the-scheduler-on)); `true`, `60` in the Render Blueprint. | No |
| `SCHEDULER_INVESTIGATIONS_PER_CYCLE`, `SCHEDULER_MESSAGES_PER_CYCLE` | `1` each on k3s and in the Blueprint. The smoke call sets both to zero for that call only. | No |
| `ATTENDFLOW_SEED_PROFILE` | `small` in `deploy/k8s/config.yaml`. The app does not read it yet; a later phase may switch it to `large` there. | No |
| `SCHEDULER_BACKLOG` | `false`. | No |
| `LLM_API_KEY_FILE` | Unset initially. On Render, use `/etc/secrets/groq-api-key` after adding the corresponding host Secret File. Set only one key source. | Path only, contents secret |
| `LLM_API_KEY` | Unset initially and on Render. For a prebuilt-image host that supplies runtime environment secrets, this is an alternative to the secret file. | Yes, if used |
| `LLM_BASE_URL`, `LLM_MODEL` | `https://api.groq.com/openai/v1`, `openai/gpt-oss-120b`. A deployed key can only use this Groq base URL. | No |
| `LLM_DIAGNOSTICS`, `LOG_FORMAT`, `LOG_LEVEL` | `off`, `json`, `INFO`. Deployment rejects diagnostics and debug logging. | No |
| `LLM_TIMEOUT_SECONDS`, `LLM_REASONING_EFFORT`, `LLM_INVESTIGATION_BUDGET_SECONDS` | `30`, `low`, `45`. | No |
| `AGENT_MAX_STEPS`, `LLM_EXTRACTION_ATTEMPTS` | `5`, `2`. | No |
| `AUTO_RESOLVE_ENABLED`, `OVERTIME_WARNING_MARGIN_HOURS` | `true`, `4`. | No |
| `NO_REPLY_ESCALATION_ENABLED`, `NO_REPLY_REMINDER_HOURS`, `NO_REPLY_SUPERVISOR_HOURS`, `NO_REPLY_ADMIN_HOURS` | `true`, `8`, `24`, `24`. The clock stays fixed in Locked mode. | No |
| `VITE_API_BASE_URL` | Leave unset in the Docker build. The built app uses the browser's origin. Local Vite dev falls back to localhost. | Public build input |
| `TEST_DATABASE_URL`, `REQUIRE_DB` | Local and CI checks only. Keep them out of the hosted service. | Test database credentials can be secret |

Render forwards Docker service environment variables to the builder as build
arguments. The Dockerfile declares no application secret arguments and copies
only the build inputs. For Groq use **Environment → Secret Files**, never a Render
build argument or a `VITE_*` variable. The Dockerfile does not mount secrets in any
build step. See [Render Docker secrets](https://render.com/docs/docker-secrets).

## Bootstrap and operate a deployment

Run the CLI in the app container or from a trusted operator terminal with the
same app version and database configuration. The container entrypoint migrates
before starting the API. If running the CLI from a local checkout against a
managed database, export the deployment's runtime values and use an operator
connection with access to that database. Keep the database credentials and
signing secret out of the repository.

```sh
python -m attendflow.scripts.auth_cli seed-demo
```

The command loads the synthetic data on an empty DB and populates missing
credentials on an existing matching demo dataset. Repeating it preserves
existing passwords and case decisions. Bootstrap works while HTTP seeding is
disabled. If the host has no shell, run it from the operator terminal using a
database URL that the terminal can reach. When using the local virtualenv, use
`uv run python -m attendflow.scripts.auth_cli seed-demo`.

Open `/login`. The operator can sign in as `priya@demo.attendflow.test`,
`ravi@demo.attendflow.test`, or `amit@demo.attendflow.test` using the demo password.
Share the password separately from the URL. The Locked profile omits the email
shortcuts.

```sh
python3 scripts/smoke-deployed.py "$URL"
# Guided demo only. Wipes the synthetic DB, then signs in again.
python3 scripts/smoke-deployed.py "$URL" --initialize reset
```

The smoke script signs in, checks the authorization boundaries and frontend,
and runs one explicitly model-free scheduler cycle. For a smoke run with zero
model calls across the service, leave the model key unset or pause the periodic
scheduler. After bootstrap, the manual run works even with the periodic scheduler
off.

## Kubernetes on k3s (the deployment target)

One amd64 VM runs k3s with Traefik (shipped with k3s), cert-manager for a Let's
Encrypt certificate, PostgreSQL 16 and the app. The manifests are in
[deploy/k8s](../deploy/k8s) (kustomize, namespace `attendflow`). CI builds the image
and pushes it to `ghcr.io/ayushsahu2004/attendflow-ai` (tags: commit SHA and `latest`)
after every green push to `main`.

| File | What it is | Applied by |
| --- | --- | --- |
| `config.yaml` | ConfigMap: Locked profile, session login, limits. The one place for non-secret settings. | `kubectl apply -k` |
| `app.yaml` | App Deployment (1 replica, `Recreate`, probes on `/healthz`, waits for the DB) + Service | `kubectl apply -k` |
| `postgres.yaml` | Postgres StatefulSet (2Gi volume, `pg_isready` checks) + ClusterIP Service | `kubectl apply -k` |
| `ingress.yaml` | Traefik Ingress with TLS + HTTP→HTTPS redirect | `kubectl apply -k` |
| `networkpolicy.yaml` | Only Traefik reaches the app; only the app reaches Postgres | `kubectl apply -k` |
| `auth.example.yaml` | Placeholder Secret, never applied | — |
| `cluster-issuers.example.yaml` | Let's Encrypt staging + prod issuers | `kubectl apply -f`, once |
| `traefik-config.example.yaml` | Keeps real client IPs for the login lockout | `kubectl apply -f`, once |

Why one replica and `Recreate`: the scheduler runs inside the API process with an
in-process lock, so two pods would run two schedulers. `Recreate` stops the old pod
before the new one starts, also during a rollout.

### 1. Create the VM

- Ubuntu 24.04 LTS, **amd64**, at least 4 GB RAM (for example `t3.medium`), 20 GB disk.
- Attach an **Elastic IP**. Your hostname is that IP with dashes plus `.sslip.io`,
  for example `54.12.34.56` → `54-12-34-56.sslip.io` (sslip.io resolves it to the IP).
- Security group: SSH (22) from your own IP only; HTTP (80) and HTTPS (443) from
  anywhere. Do not open the Kubernetes API port 6443.

### 2. Install k3s

On the VM. Pick a current version from the [k3s releases](https://github.com/k3s-io/k3s/releases)
page (or leave `INSTALL_K3S_VERSION` out to get the stable channel):

```sh
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="<k3s version>" sh -
mkdir -p ~/.kube && sudo k3s kubectl config view --raw > ~/.kube/config && chmod 600 ~/.kube/config
kubectl get nodes
```

Copy the repo to the VM (for example `git clone` with your GitHub login), then work
from the repo root. Keep real client IPs for the per-IP login lockout:

```sh
kubectl apply -f deploy/k8s/traefik-config.example.yaml
kubectl -n kube-system rollout status deploy/traefik --timeout=5m
```

### 3. Install cert-manager and the issuers

Pick a current version from the [cert-manager releases](https://github.com/cert-manager/cert-manager/releases):

```sh
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/<cert-manager version>/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=5m
sed -i 's/you@example.com/<your email>/' deploy/k8s/cluster-issuers.example.yaml
kubectl apply -f deploy/k8s/cluster-issuers.example.yaml
```

Set your hostname in the Ingress (it appears twice; this changes both):

```sh
sed -i 's/203-0-113-10.sslip.io/<elastic-ip-with-dashes>.sslip.io/g' deploy/k8s/ingress.yaml
```

### 4. Create the secrets

The image is private (the repo is private). Create a GitHub **classic personal access
token** with only the `read:packages` scope (GitHub → Settings → Developer settings →
Personal access tokens). The first image exists after CI's `image` job has run once on
`main`.

```sh
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export ATTENDFLOW_SESSION_SECRET="$(openssl rand -hex 32)"
export ATTENDFLOW_DEMO_PASSWORD="$(openssl rand -hex 24)"
export GHCR_USERNAME=<your GitHub user name>
read -rs GHCR_TOKEN && export GHCR_TOKEN
sh scripts/k8s-create-secrets.sh
```

The script creates the `attendflow` namespace, the `attendflow-secrets` Secret (it builds
`DATABASE_URL` from `POSTGRES_PASSWORD`) and the `ghcr-pull` image pull secret. It passes
the values to kubectl as files and prints none of them. Save the demo password in your
password manager: it is the sign-in password for every demo account. Leave the Groq key
out for now (step 8 adds it), so the first checks make no model calls.

`POSTGRES_PASSWORD` only takes effect when the database volume is first created. Run the
script again later with the **same** value, or the app can no longer connect.

### 5. Deploy

```sh
kubectl apply -k deploy/k8s
kubectl -n attendflow rollout status statefulset/attendflow-db --timeout=5m
kubectl -n attendflow rollout status deploy/attendflow --timeout=5m
kubectl -n attendflow logs deploy/attendflow --tail=50
```

The app's init container waits for Postgres, then the app migrates the database and
starts. The startup probe allows about three minutes for that.

### 6. Bootstrap the demo accounts

```sh
kubectl -n attendflow exec deploy/attendflow -- python -m attendflow.scripts.auth_cli seed-demo
```

It loads the synthetic data into the empty database, runs detection once and sets the
demo passwords. Repeating it keeps existing passwords and cases.

### 7. Certificate, then the smoke test

```sh
kubectl -n attendflow get certificate        # READY True with the staging issuer
sed -i 's/letsencrypt-staging/letsencrypt-prod/' deploy/k8s/ingress.yaml
kubectl apply -k deploy/k8s
kubectl -n attendflow delete secret attendflow-tls   # forces a new, trusted certificate
kubectl -n attendflow get certificate -w             # wait for READY True, then Ctrl+C
```

From your laptop (it asks for the demo password):

```sh
python3 scripts/smoke-deployed.py "https://<elastic-ip-with-dashes>.sslip.io"
```

**Cold-start check:** restart the app and time it until it is ready, then run the smoke
test again.

```sh
kubectl -n attendflow rollout restart deploy/attendflow
time kubectl -n attendflow rollout status deploy/attendflow --timeout=5m
```

### 8. Add the Groq key and check connectivity

Re-run the script with the **same** values plus the key. If you no longer have them in
your shell, load them from the cluster without printing them:

```sh
for k in POSTGRES_PASSWORD ATTENDFLOW_SESSION_SECRET ATTENDFLOW_DEMO_PASSWORD; do
  export "$k=$(kubectl -n attendflow get secret attendflow-secrets -o jsonpath="{.data.$k}" | base64 -d)"
done
read -rs LLM_API_KEY && export LLM_API_KEY
sh scripts/k8s-create-secrets.sh
kubectl -n attendflow rollout restart deploy/attendflow
kubectl -n attendflow rollout status deploy/attendflow --timeout=5m
kubectl -n attendflow exec deploy/attendflow -- python -m attendflow.scripts.llm_smoke_test
```

The last command sends one prompt to Groq (one model call) and prints the reply,
never the key. Then sign in as Priya and press Refresh on the daily briefing: the label
"Written by the LLM from verified facts" means the model answered and passed the checks.

### 9. Later: turn the scheduler on

The scheduler is **off** at first. Detection, auto-resolve and every button still work
without it (see below). To turn it on, change one line and roll out the app:

```sh
sed -i 's/SCHEDULER_ENABLED: "false"/SCHEDULER_ENABLED: "true"/' deploy/k8s/config.yaml
kubectl apply -k deploy/k8s
kubectl -n attendflow rollout restart deploy/attendflow
kubectl -n attendflow rollout status deploy/attendflow --timeout=5m
```

`Recreate` stops the old pod (it finishes a running cycle first, up to 60 s) before the
new one starts, so two schedulers never run. To try it without a rollout, Priya can press
Start on `/admin`; that lasts until the next restart.

**What it costs in Groq calls.** Each cycle (every 60 s) runs detection with no model
call. Then, only for cases first detected after the scheduler started
(`SCHEDULER_BACKLOG=false`):

- up to `SCHEDULER_INVESTIGATIONS_PER_CYCLE` (1) investigations, each at most
  `AGENT_MAX_STEPS` (5) model calls within its 45 s budget;
- up to `SCHEDULER_MESSAGES_PER_CYCLE` (1) worker messages, one call each;
- Priya's scheduled briefing at most once per workflow day, at most 2 calls, counted in
  `BRIEFING_MAX_LLM_CALLS_PER_DAY` (40).

So the worst case is about 6 calls per minute while new cases keep appearing. In the
Locked profile the clock is fixed and device punches are off, so new cases appear only
when a person's approved fix creates one. Most cycles make no model call. The client
retries HTTP 429/5xx twice per call; failures fall back to templates.

### Operate

```sh
kubectl -n attendflow exec deploy/attendflow -- python -m attendflow.scripts.auth_cli seed-demo
kubectl -n attendflow exec -it deploy/attendflow -- python -m attendflow.scripts.auth_cli set-password E001
kubectl -n attendflow exec deploy/attendflow -- python -m attendflow.scripts.auth_cli unlock --email amit@demo.attendflow.test
kubectl -n attendflow exec deploy/attendflow -- python -m attendflow.scripts.auth_cli unlock --ip 192.0.2.10
```

Add `--email employee@example.com` when setting credentials for someone without
an email. The password command prompts without echo and revokes that employee's
sessions. Unlock runs in the same container as the API (the lockout state is in the
pod's `/tmp`). If both the email and IP are locked, clear both. Login and logout are
outside the attendance activity trail. Successful and failed logins appear in the
ordinary application log.

With `ATTENDFLOW_TRUSTED_PROXY=true`, the app uses the rightmost IP in
`X-Forwarded-For`, which Traefik sets. The NetworkPolicy makes Traefik the only way in.
The browser Origin must match the Host. To pin a specific image instead of `latest`:

```sh
kubectl -n attendflow set image deploy/attendflow attendflow=ghcr.io/ayushsahu2004/attendflow-ai:<commit sha>
```

`kubectl apply -k` puts `latest` back.

### Render (optional, not used)

Deploy the Locked profile from `render.yaml` and supply the two independent
secrets when prompted. Leave the model key unset for initial verification. After
the app reports a healthy `/healthz`, run the CLI bootstrap with access to its
database and run the smoke script against the public HTTPS URL. When switching
profiles, wait for any running scheduler cycle to complete before redeploying.

## Fallback on Koyeb and Neon

1. In Neon choose **New Project**, select a region near the Koyeb region and create
   a Free PostgreSQL project. Under **Connect**, copy the **Direct** URL with TLS.
2. Build and push the same image from your own machine or CI to a registry you
   control. For example, after signing into the registry:
   `docker buildx build --platform linux/amd64 -t ghcr.io/YOUR_USER/attendflow-demo:16.5 --push .`
   This build receives no app secrets.
3. In Koyeb choose **Create Web Service → Docker**. Select the registry image
   (add registry credentials in **Secrets** if private), choose the Free instance,
   and set HTTP port `10000` at path `/` with HTTP health check `/healthz`.
   Keep one replica. Confirm only free resources are selected before deploying.
4. In the service's environment variables assign the Neon URL, session signing secret, and demo password
   as secrets. Apply the Locked values and shared scheduler settings above. Deploy,
   then repeat the bootstrap and smoke steps using the Koyeb HTTPS URL. Leave Groq
   unset until after the smoke check. See [Koyeb registry deploy](https://www.koyeb.com/docs/build-and-deploy/prebuilt-docker-images).

## Verify the image locally on a Mac

Open Docker Desktop and use a shell from the repo root. These names are for an
isolated test stack. PostgreSQL has no published host port and the web port binds
only to loopback.

```sh
docker build -t attendflow-demo:16.5 .
docker network create attendflow-dryrun
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export DATABASE_URL="postgres://demo:${POSTGRES_PASSWORD}@attendflow-dryrun-db:5432/attendflow_demo"
export ATTENDFLOW_DEMO_PASSWORD="$(openssl rand -hex 24)"
export ATTENDFLOW_SESSION_SECRET="$(openssl rand -hex 32)"
docker run -d --name attendflow-dryrun-db --network attendflow-dryrun \
  -e POSTGRES_USER=demo -e POSTGRES_DB=attendflow_demo -e POSTGRES_PASSWORD postgres:16
until docker exec attendflow-dryrun-db pg_isready -h 127.0.0.1 -U demo -d attendflow_demo; do
  sleep 2
done

docker run -d --name attendflow-dryrun-app --network attendflow-dryrun \
    -p 127.0.0.1:8016:10000 -e DATABASE_URL -e ATTENDFLOW_DEMO_PASSWORD \
    -e ATTENDFLOW_SESSION_SECRET -e ATTENDFLOW_COOKIE_SECURE=false \
    -e ATTENDFLOW_ENABLE_SEED=false -e ATTENDFLOW_DEMO_MODE=false \
    -e ATTENDFLOW_DEMO_RESET_ENABLED=false -e ATTENDFLOW_DEMO_EXTRA_WEEK=false \
    -e LLM_DIAGNOSTICS=off -e SCHEDULER_ENABLED=true attendflow-demo:16.5
docker logs attendflow-dryrun-app
curl --retry 10 --retry-connrefused --retry-delay 2 -fsS http://localhost:8016/healthz
```

To bootstrap and verify in Locked mode:

```sh
docker exec attendflow-dryrun-app python -m attendflow.scripts.auth_cli seed-demo
python3 scripts/smoke-deployed.py http://localhost:8016
```

Open `http://localhost:8016/dashboard` to verify rendering in your browser.
Use the generated password from the shell if prompted. Once finished:

```sh
docker rm -f attendflow-dryrun-app attendflow-dryrun-db
docker network rm attendflow-dryrun
unset POSTGRES_PASSWORD DATABASE_URL ATTENDFLOW_DEMO_PASSWORD ATTENDFLOW_SESSION_SECRET
```


## Run session mode locally

Set `DATABASE_URL` to a local disposable PostgreSQL database. From the repo root:

```sh
uv sync --locked
export ATTENDFLOW_AUTH_MODE=session ATTENDFLOW_COOKIE_SECURE=false
export ATTENDFLOW_DEMO_MODE=true ATTENDFLOW_DEMO_RESET_ENABLED=true
export ATTENDFLOW_SESSION_SECRET="$(openssl rand -hex 32)"
export ATTENDFLOW_DEMO_PASSWORD="$(openssl rand -hex 24)"
uv run alembic upgrade head
uv run python -m attendflow.scripts.auth_cli seed-demo
uv run attendflow-api --port 8011
```

From a second terminal:

```sh
npm --prefix frontend ci
ATTENDFLOW_VITE_PROXY=http://127.0.0.1:8011 VITE_API_BASE_URL=/ npm --prefix frontend run dev -- --port 5181
```

Open `http://localhost:5181/login`. To use a human-selected local password, run
`uv run python -m attendflow.scripts.auth_cli set-password E001 --email amit@demo.attendflow.test`
with the same database environment and follow the prompts.
