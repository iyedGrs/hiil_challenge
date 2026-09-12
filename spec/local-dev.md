# Local development guide

Status: planned development environment. **No application, Dockerfiles, Compose file, seed command or server has been created or started.** The commands below define how the future implementation should run; they are not runnable against this documentation-only workspace yet.

Owners: API owns the future Docker/environment/database setup. UI owns the frontend startup command and browser proxy. Both maintain the integrated run instructions.

Read [frontend.md](frontend.md), [backend.md](backend.md) and [progress.md](progress.md) first. Backend section B9 is the shared API contract.

## L1. Recommended environment

Use Docker Compose for a reproducible integrated demo. Use browser fixtures while frontend work is independent. Do not pay for model calls to develop screen layouts.

Proposed runtime baselines: Node.js 22, Python 3.11 and PostgreSQL 16. These are compatibility choices, not a claim to be the latest versions. Pin tested package versions and commit lockfiles when development is authorized.

| Future service | Role | Local access |
| --- | --- | --- |
| `web` | React/Vite development server | `http://localhost:5173` |
| `api` | FastAPI, sessions, uploads and read endpoints | `http://localhost:8000`; browser normally uses web proxy |
| `worker` | Jobs, extraction/OCR, AI, validation and export | No public port |
| `db` | PostgreSQL state and job queue | Internal `db:5432`; do not expose by default |

One API process and one worker are enough. Use a persistent DB volume and a private file volume mounted by API and worker. The web container must not receive file storage or provider credentials.

Browser calls relative `/api/...`; Vite proxies to `api:8000` in Compose or `127.0.0.1:8000` when Vite runs on the host. This preserves a single browser origin for cookies and CSRF behavior. FastAPI includes the `/api` prefix; the proxy must not remove it.

Development sessions use HttpOnly cookies, explicit SameSite policy and CSRF tokens on mutations. `Secure=false` is a local HTTP exception only; use HTTPS and secure cookies in deployed environments. Fixture authentication is isolated and visibly marked.

## L2. Future repository layout

Only `spec/` documents currently belong to this deliverable. Create the following implementation assets later:

| Path | Owner | Future purpose |
| --- | --- | --- |
| `frontend/` | UI | React/TypeScript app, `npm run dev`, lockfile |
| `frontend/src/api/` | UI | Fixture/HTTP adapters matching B9 |
| `backend/app/main.py` | API | FastAPI entry point |
| `backend/app/worker.py` | API | Worker entry point |
| `backend/app/seed_demo.py` | API | Idempotent synthetic data/account seeding |
| `backend/app/legal_packs/` | API | Versioned checklist/reference files and review labels |
| `backend/migrations/` | API | Alembic schema migrations |
| `backend/tests/` | API | Deterministic, validation and access-boundary checks |
| `fixtures/` | API, with UI agreement | Synthetic source documents and expected outcomes |
| `compose.yaml` | API | `web`, `api`, `worker`, `db` |
| `.env.example` | API | Nonsecret environment documentation |
| `.env` | Each contributor locally | Private credentials; git-ignored |

Do not create an unrelated `shared` service or a second backend just for AI.

## L3. Environment contract

This table describes the future `.env.example`; it is not a request to share secrets.

| Variable | Default or expected value | Consumer |
| --- | --- | --- |
| `APP_ENV` | `development` | API/worker |
| `DATABASE_URL` | PostgreSQL URL using host `db` in Compose; driver matches installed SQLAlchemy driver | API/worker |
| `POSTGRES_DB` | `dispute_demo` | Database |
| `POSTGRES_USER` | `dispute_demo` | Database |
| `POSTGRES_PASSWORD` | Developer-generated local secret | Database/API/worker |
| `SESSION_SECRET` | Developer-generated random secret, never a committed value | API |
| `COOKIE_SECURE` | `false` locally; `true` with HTTPS | API |
| `APP_ORIGIN` | `http://localhost:5173` | API |
| `FILE_STORAGE_ROOT` | `/data/private` in containers | API/worker |
| `AI_MODE` | `fixture` by default; `live` only when enabled deliberately | API/worker |
| `AI_PROVIDER` | Selected provider; not yet confirmed | Worker/intake adapter |
| `AI_MODEL` | Accessible tested model ID; not yet confirmed | Worker/intake adapter |
| `AI_API_KEY` | Provider credential, never frontend-visible | Worker/intake adapter |
| `AI_ENDPOINT` | Optional provider endpoint, required if the chosen provider needs it | Worker/intake adapter |
| `AI_DEMO_BUDGET_USD` | `0` in fixture mode; explicit cap needed for live mode | API/worker |
| `AI_MAX_CONCURRENCY` | `1` | Worker |
| `LEGAL_PACK_VERSION` | `tn-goods-v1` initial asset version | API/worker |
| `MAX_CASE_FILES` | `10` | API/worker |
| `MAX_CASE_PAGES` | `30` | API/worker |
| `MAX_FILE_BYTES` | `10485760` | API |
| `MAX_CASE_BYTES` | `52428800` | API |
| `OCR_LANGUAGES` | `fra+ara+eng` | Worker |
| `API_PROXY_TARGET` | `http://api:8000` in Compose | Vite server, not browser secret |
| `VITE_DATA_MODE` | `fixture` or `http` | Frontend |

Fixture mode must avoid provider calls entirely, including health checks and intake. Live mode must fail configuration validation if credentials, model or spending ceiling are absent. Do not silently switch to fixture results after a live provider failure.

## L4. Planned Docker startup

Prerequisite: both contributors have subsequently implemented the layout, Dockerfiles, Compose services, migration setup, seed script and commands named here.

Each contributor creates their private `.env` from the future `.env.example` and supplies local values. Do not include real case data or API keys in screenshots, fixtures or source control.

Run from the future repository root:

```bash
docker compose build
docker compose up -d --wait db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.seed_demo
docker compose up -d api worker web
docker compose ps
```

The backend image's working directory and installed application package must make the Alembic and `python -m app...` commands valid. `api` should start through `uvicorn app.main:app --host 0.0.0.0 --port 8000`; `worker` through `python -m app.worker`. Vite must listen on `0.0.0.0:5173` inside its container.

Compose must use a database health check and healthy dependency condition. A running container is not enough to prove PostgreSQL is accepting requests; Docker documents this distinction in its [startup-order guide](https://docs.docker.com/compose/how-tos/startup-order/).

Do not run migrations independently in every API/worker process. Run the single migration step before starting them, as above. Mount the same private files volume into API and worker. Install the PDF renderer and Tesseract language files in the worker image.

## L5. Independent work before integration

### UI work

After the frontend package exists, set its local `VITE_DATA_MODE=fixture` and run in `frontend/`:

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

`npm ci` requires a committed lockfile; creating that initial package/lockfile is a later development task. Match all fixtures to B9. No backend or live AI is required in browser fixture mode.

### API work

Use Docker `db`, `api` and `worker` in backend fixture mode, then test API operations through `http://localhost:8000/docs`. Seed two preparers and one reviewer. Validated fixture output should pass through the real validators, persistence and submission logic rather than bypass them.

Mock authentication shortcuts must not replace the integrated server authorization. Keep intentionally invalid model-output fixtures for backend validation tests; never publish them directly as demo UI data.

### Integrated mode without spending credits

Set `VITE_DATA_MODE=http` and `AI_MODE=fixture`. Restart API/worker and restart Vite if its environment changed. This exercises real sessions, documents, jobs, validators, reassessment and reviewer handoff using clearly labelled deterministic AI fixtures.

### Live demonstration

After provider access and fixture acceptance checks pass, set `AI_MODE=live`, the actual provider/model/endpoint, private credential and a small positive spending ceiling. Restart the relevant services. Run a single known synthetic case and inspect measured usage before rehearsing additional cases.

Run only one live worker for the demo. Do not rely on assumed provider support or latency; log the first successful result in progress.md.

## L6. Planned verification and troubleshooting

```bash
curl http://localhost:8000/api/health/live
curl http://localhost:8000/api/health/ready
docker compose logs --tail=100 api worker
```

These checks become useful after implementation. Logs must redact secrets and document content.

| Symptom | Check |
| --- | --- |
| Browser cannot reach API | Vite proxy target differs for host versus container execution |
| Login does not persist | Proxy, cookie host/flags and request credentials; no mixed `localhost`/`127.0.0.1` session origins |
| Mutation rejected | Valid CSRF token and current revision |
| Jobs remain queued | Worker running, DB lease and permissions; no provider calls needed to diagnose a queued job |
| Scan facts all rejected | OCR language installation, stored page text and quote matching; do not weaken validation to make demo green |
| A corrected upload changes nothing | Reassessment revision, active document registry and cache version |
| Provider limit reached | Show retryable error; preserve case; do not silently generate fixture answers |
| Reviewer sees no case | Submission is explicit and recipient assignment must match signed-in reviewer |

Stop the future environment with `docker compose stop`; containers and named data volumes remain. Do not use `docker compose down -v` unless intentionally deleting disposable demo data. No such command has been run for this task.

API owns final verification that these commands match the implemented entry points; UI verifies that the browser can complete the entire loop from a fresh startup.
