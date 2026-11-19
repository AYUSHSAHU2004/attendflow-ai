# Phase 16.5 private demo deploy

Use a disposable PostgreSQL database and the synthetic CSVs in this repository.
The shared HTTPS password protects the frontend, assets, API and API docs. The
only public application route is the minimal read-only `/healthz`. Sign in as
`demo` with the password from the operator. Anyone who knows that password can
choose a demo actor with `X-Actor-Id`. Share it separately from the URL and rotate
it after the rehearsal. The hosted app uses the existing fixed actors by page.
How judges switch among Priya, Ravi, Amit and Neha remains open for Phase 22.

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
require the same strong password, use same-origin URLs, keep diagnostics off and
use synthetic data.

| Setting | Locked | Guided demo |
| --- | --- | --- |
| `ATTENDFLOW_ENABLE_SEED` | `false` | `false` |
| `ATTENDFLOW_DEMO_MODE` | `false` | `true` |
| `ATTENDFLOW_DEMO_RESET_ENABLED` | `false` | `true` |
| `ATTENDFLOW_DEMO_EXTRA_WEEK` | `false` | `true` |
| `DEVICE_API_KEY` | Unset | Unset |

Guided mode enables the simulator, demo clock and gated reset. After reset, the
extra week is available for the payroll sign-off demo. Moving the workflow clock
leaves the attendance cutoff fixed. Locked mode alone does not undo any simulated
changes or delete previously seeded synthetic records.

### Runtime and build variables

| Variable | Deployed value or default | Secret? |
| --- | --- | --- |
| `DATABASE_URL` | Required runtime URL. Use Render's internal URL or Neon's direct URL including `sslmode=require`. Both `postgres://` and `postgresql://` normalize to `postgresql+psycopg://`. | Yes |
| `ATTENDFLOW_DEPLOYED` | `true`, enforced by the container launcher. | No |
| `ATTENDFLOW_DEMO_PASSWORD` | Required. Generate with `openssl rand -hex 24`. | Yes |
| `PORT` | Provider-assigned HTTP port, default `10000`. Published HTTPS is terminated by the provider. | No |
| `ATTENDFLOW_ENABLE_SEED`, `ATTENDFLOW_DEMO_MODE`, `ATTENDFLOW_DEMO_RESET_ENABLED`, `ATTENDFLOW_DEMO_EXTRA_WEEK` | Use the profile above. Seed and reset wipe the DB. Enable seed only to load a disposable synthetic DB. | No |
| `DEVICE_API_KEY` | Leave unset in both profiles. To enable external punch ingestion deliberately, use a separate random value and send both demo Basic Auth and `X-Device-Key`. | Yes, if used |
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

## Deploy on Render

1. Commit and push this phase to the Git branch you want to deploy. Sign into Render,
   connect that Git provider, and choose **New → Blueprint**.
2. Select the repo and branch with the root `render.yaml`. Review the proposed
   **Free** Docker web service and **Free** PostgreSQL database in the same region.
   Supply a new `ATTENDFLOW_DEMO_PASSWORD` in the Blueprint prompt, then click
   **Deploy Blueprint**. Leave Groq unset. See [Render Blueprint setup](https://render.com/docs/infrastructure-as-code).
3. Open **Web Services → attendflow-demo → Events/Logs**. Check that Alembic and
   Uvicorn start, that the plan is Free, and that the health check path is `/healthz`.
   Use the assigned HTTPS URL. `/healthz` should return `{"status":"ok"}`; visiting
   `/dashboard` should prompt for Basic Auth. The initial database has schema only.
4. To populate it, use the synthetic seed. On the first empty database, skip the
   pause command because the scheduler API needs seeded actors and there are no
   cases to process. With an existing seeded database, pause the scheduler before
   each environment redeploy:

   ```sh
   URL=https://your-service.onrender.com
   curl -fsS --user demo -H 'X-Actor-Id: E201' -X POST "$URL/api/admin/scheduler/stop"
   curl -fsS --user demo -H 'X-Actor-Id: E201' "$URL/api/admin/scheduler"
   ```

   Each curl prompts for the password. In **Environment**, set
   `ATTENDFLOW_ENABLE_SEED=true`, save and deploy, then run:

   ```sh
   curl -fsS --user demo -X POST "$URL/api/seed"
   ```

   This seeds a disposable database and wipes any previous contents. Once it succeeds,
   stop the scheduler and confirm the cycle has finished. Set
   `ATTENDFLOW_ENABLE_SEED=false` and save and deploy again. Keep the other Locked
   values. The smoke cycle generates the initial findings if it runs before the timer.
5. From the repo root run `python3 scripts/smoke-deployed.py "$URL"` and enter the demo
   password. It checks the public health probe, unauthenticated refusals, built
   frontend and JavaScript, Priya's dashboard, Amit's inbox, and one scheduler cycle.
   That cycle skips investigations and messaging even with a Groq key. It still runs
   detection and the no-reply ladder. An independently enabled periodic cycle can
   still do normal model work. Exit zero means every check printed PASS.
6. For a guided rehearsal, pause the scheduler before switching the three profile flags
   in **Environment** and deploying. With seeded actors, run
   `python3 scripts/smoke-deployed.py "$URL" --initialize reset` only if you want to
   wipe and reload the synthetic data. On an empty replacement DB, arm and run seed
   first. Return to Locked after the rehearsal.
7. After the baseline is working, optionally add the key in **Environment → Secret
   Files → Add Secret File**, name it `groq-api-key`, and save the key as its contents.
   Set `LLM_API_KEY_FILE=/etc/secrets/groq-api-key` and redeploy with diagnostics off.
   Phase 16.5 smoke does not verify Groq connectivity. Share the demo URL and password
   over separate channels.

If the database expires, follow Render's replacement instructions, confirm the
web service points to the new internal URL, and repeat the bootstrap. On cold
starts the smoke script waits for health. For startup failure, check the deploy
logs, connection URL/region, binding to `PORT`, secret values, and migration
permissions. Docker migration failures report a safe error category. If the
cycle is busy, wait for it to finish and rerun the locked smoke.

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
4. In the service's environment variables assign the Neon URL and demo password
   as secrets. Apply the Locked values and shared scheduler settings above. Deploy,
   then repeat the bootstrap and smoke steps using the Koyeb HTTPS URL. Leave Groq
   unset until after the smoke check. See [Koyeb registry deploy](https://www.koyeb.com/docs/build-and-deploy/prebuilt-docker-images).

## Verify the image locally on a Mac

The image build and container runtime are **unverified** until these commands run.
Open Docker Desktop and use a shell from the repo root. These names are for an
isolated test stack. PostgreSQL has no published host port and the web port binds
only to loopback.

```sh
docker build -t attendflow-demo:16.5 .
docker network create attendflow-dryrun
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export DATABASE_URL="postgres://demo:${POSTGRES_PASSWORD}@attendflow-dryrun-db:5432/attendflow_demo"
export ATTENDFLOW_DEMO_PASSWORD="$(openssl rand -hex 24)"
docker run -d --name attendflow-dryrun-db --network attendflow-dryrun \
  -e POSTGRES_USER=demo -e POSTGRES_DB=attendflow_demo -e POSTGRES_PASSWORD postgres:16
until docker exec attendflow-dryrun-db pg_isready -h 127.0.0.1 -U demo -d attendflow_demo; do
  sleep 2
done

start_dryrun() {
  docker run -d --name attendflow-dryrun-app --network attendflow-dryrun \
    -p 127.0.0.1:8016:10000 -e DATABASE_URL -e ATTENDFLOW_DEMO_PASSWORD \
    -e "ATTENDFLOW_ENABLE_SEED=$1" -e ATTENDFLOW_DEMO_MODE=false \
    -e ATTENDFLOW_DEMO_RESET_ENABLED=false -e ATTENDFLOW_DEMO_EXTRA_WEEK=false \
    -e LLM_DIAGNOSTICS=off -e SCHEDULER_ENABLED=true attendflow-demo:16.5
}
start_dryrun false
docker logs attendflow-dryrun-app
curl --retry 10 --retry-connrefused --retry-delay 2 -fsS http://localhost:8016/healthz
```

To seed once and then verify in Locked mode:

```sh
docker rm -f attendflow-dryrun-app
start_dryrun true
curl --retry 10 --retry-connrefused --retry-delay 2 -fsS http://localhost:8016/healthz
curl -fsS --user demo -X POST http://localhost:8016/api/seed
docker rm -f attendflow-dryrun-app
start_dryrun false
python3 scripts/smoke-deployed.py http://localhost:8016
```

Open `http://localhost:8016/dashboard` to verify rendering in your browser.
Use the generated password from the shell if prompted. Once finished:

```sh
docker rm -f attendflow-dryrun-app attendflow-dryrun-db
docker network rm attendflow-dryrun
unset POSTGRES_PASSWORD DATABASE_URL ATTENDFLOW_DEMO_PASSWORD
```
