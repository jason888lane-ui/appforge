# AppForge

Enterprise autonomous software-development platform. AppForge is an independent application and has no runtime dependency on other projects.

## Current implementation

AppForge now includes a FastAPI dashboard/API, six-role deterministic agent planner, tenant-scoped persistent projects and agent-run records, signed bearer authentication, OpenAI-compatible and Anthropic model adapters, an opt-in Docker code sandbox, plan-only AWS/Azure/GCP adapters, and production approval checks.

This is an implementation foundation, not yet a production-ready autonomous coding platform. The agent planner still proposes work; model calls are explicit API requests, not autonomous agent loops. The API persistence layer now supports SQLite for direct local runs and PostgreSQL through SQLAlchemy. Workspace roles are owner, developer, and viewer; role checks are enforced server-side. Enterprise OIDC/SSO, MFA, managed database migrations, audit tamper-evidence, durable background queues, and production deployment workflows remain future work.

## Run locally

Requirements: Docker Engine/Desktop with Compose.

```bash
git clone https://github.com/jason888lane-ui/appforge.git
cd appforge
cp .env.example .env
# Set APP_AUTH_SECRET to a unique random value before sharing the service.
docker compose up --build
```

Open http://localhost:8000 for the dashboard and http://localhost:8000/docs for API docs.

Without Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --app-dir backend --reload
```

## Authentication and tenant isolation

1. Register a tenant owner with `POST /api/v1/auth/register`.
2. Use the returned bearer token for protected endpoints.
3. Create projects with `POST /api/v1/projects`.
4. Create persisted agent proposals with `POST /api/v1/agent-runs`.
5. Add tenant team members as an owner with `POST /api/v1/team/members` and assign `developer` or `viewer`.
6. List only the authenticated tenant's projects and runs.

Role matrix: owners can administer the team and use all current workspace APIs; developers can create projects and agent proposals and use configured model calls; viewers can read workspace projects and runs. Sandbox execution is owner-only. Role changes are read from the database on each authenticated request so permission changes take effect without waiting for token expiry.

The tenant ID is derived from the signed token, never accepted as a caller-supplied tenant selector. Project access is checked against that tenant. Passwords are PBKDF2-HMAC-SHA256 hashes. Planning, agent-run preview, cloud-plan preview, and governance-check APIs require workspace authentication; production approval checks are owner-only and record the authenticated owner as approver rather than trusting a caller-supplied identity. Approval checks never execute deployments. The built-in token signer is a minimal first-party baseline; production must use a managed identity provider/enterprise OIDC and a secret manager.

## Model providers

Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in the runtime environment. Then call `POST /api/v1/models/complete` with a provider and prompt. Model calls incur provider charges and should be enabled only after setting the relevant key and usage limits. Keys are read from environment variables and are not persisted.

## Isolated code execution

The Docker sandbox is disabled by default. To opt in, set `APP_ENABLE_SANDBOX=true` and ensure the host Docker daemon already has `python:3.12-alpine` available. Sandbox runs use `--pull=never`, no network, read-only filesystem, dropped capabilities, no-new-privileges, memory/CPU/PID limits, a read-only source mount, and a 20-second maximum timeout. This is a defense-in-depth development sandbox, not a substitute for a hardened multi-tenant execution service or dedicated VM isolation.
The sandbox runner is intentionally not connected to the API container's host Docker socket. The sandbox endpoint can run only where the API process has the Docker CLI and access to a dedicated Docker daemon with the image preloaded. In the supplied Compose deployment, the endpoint remains unavailable (503) even if the feature flag is enabled. Do not mount the host `docker.sock` into the web API; deploy a separately isolated sandbox worker before enabling execution in a containerized or shared environment.


## Safety boundaries

- Cloud adapters generate previews only. No cloud account is connected and no infrastructure is provisioned.
- Production deployment/apply remains disabled pending explicit human approval and a future auditable deployment service.
- Model output is untrusted input; never execute it outside the sandbox.
- Do not commit API keys, signing secrets, customer code, or production data.
- Direct local API runs use SQLite by default. Docker Compose starts a local PostgreSQL 16 service and persists its data in a named volume. The current schema initializer is a bootstrap mechanism, not a versioned migration system; add Alembic migrations and backups before production use.

## Verification

```bash
ruff check backend
pytest -q
```
