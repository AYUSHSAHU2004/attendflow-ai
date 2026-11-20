# Deploy AttendFlow with employee sessions

Use a disposable PostgreSQL database and the synthetic CSVs for demos. Employees
sign in with their email and the password supplied by the operator. The database
determines each employee's role. Session-mode API requests ignore `X-Actor-Id`.
`/healthz`, the sign-in page, and its frontend assets are public. The API docs
and schema URLs are disabled in session mode.

## Hosting options

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
| `SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_SECONDS` | `true`, `60` in the Blueprint. | No |
| `SCHEDULER_INVESTIGATIONS_PER_CYCLE`, `SCHEDULER_MESSAGES_PER_CYCLE` | `1` each in the Blueprint. The smoke call sets both to zero for that call only. | No |
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

### Kubernetes behind Traefik

Use [the ConfigMap and Secret example](../deploy/k8s/auth.example.yaml) as
`envFrom` inputs for the existing workload. Populate the Secret out of band.
Keep one replica, one Uvicorn worker, and a writable temporary directory shared
by the app and CLI in the same container. Terminate HTTPS in Traefik, preserve
the original Host, and restrict app ingress to the trusted proxy. With
`ATTENDFLOW_TRUSTED_PROXY=true`, the app uses the rightmost IP supplied by this
single proxy hop. Otherwise it uses the socket IP. The browser Origin must
match the Host, including an explicit port if present. The public HTTPS
scheme is represented by the configured Secure cookie flag.

```sh
kubectl exec deploy/attendflow -- python -m attendflow.scripts.auth_cli seed-demo
kubectl exec -it deploy/attendflow -- python -m attendflow.scripts.auth_cli set-password E001
kubectl exec deploy/attendflow -- python -m attendflow.scripts.auth_cli unlock --email amit@demo.attendflow.test
kubectl exec deploy/attendflow -- python -m attendflow.scripts.auth_cli unlock --ip 192.0.2.10
```

Add `--email employee@example.com` when setting credentials for someone without
an email. The password command prompts without echo and revokes that employee's
sessions. Unlock runs in the same container as the API. If both the email and
IP are locked, clear both. Login and logout are outside the attendance activity
trail. Successful and failed logins appear in the ordinary application log.

### Render

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
