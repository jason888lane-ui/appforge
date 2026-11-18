# AppForge

Enterprise autonomous software-development platform. AppForge is independent and has no runtime dependency on any other application.

## Current status

**Foundation stage.** This repository provides a containerized FastAPI service, an explicit production-approval policy, automated tests, and CI. It is not yet a complete autonomous coding platform and does not deploy cloud resources.

## Start locally

Requirements: Docker Desktop or Docker Engine with Compose.

```bash
git clone https://github.com/jason888lane-ui/appforge.git
cd appforge
docker compose up --build
```

API: http://localhost:8000 · OpenAPI: http://localhost:8000/docs · Health: http://localhost:8000/health

Run tests without Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Safety boundary

- Planning and validation are separate from execution.
- Production actions require explicit approval by an authorized human.
- No production deployment endpoint or cloud credentials are included in this foundation.
- Never commit secrets. Use a managed secret store when provider integrations are added.
- Cloud adapters must default to plan-only behavior until explicitly enabled.

## Planned milestones

1. API, Docker development environment, CI, and safety policy.
2. Persistent projects, jobs, audit events, and tenant-scoped authorization.
3. Agent orchestration with bounded tools, budgets, and sandboxed workspaces.
4. GitHub branch/PR workflows and isolated code execution.
5. Multi-cloud plan adapters (AWS, Azure, Google Cloud) with approval-gated apply.
6. Enterprise identity, policy administration, observability, and operational hardening.

See [docs/architecture.md](docs/architecture.md) and [docs/security.md](docs/security.md).
