# AppForge

Enterprise autonomous software-development platform. AppForge is independent and has no runtime dependency on any other application.

## Current status

**Early implementation.** The repository includes a FastAPI service, browser dashboard, six-role deterministic agent planner, plan-only adapters for AWS/Azure/Google Cloud, a production-approval policy, automated tests, and GitHub Actions CI. This is not yet a production-ready autonomous coding platform: agents do not call LLMs, execute code, or deploy infrastructure.

## Start locally

Requirements: Docker Desktop or Docker Engine with Compose.

```bash
git clone https://github.com/jason888lane-ui/appforge.git
cd appforge
docker compose up --build
```

Open http://localhost:8000 for the dashboard, http://localhost:8000/docs for the API, and http://localhost:8000/health for health status.

Run tests without Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check backend
```

## Included capabilities

- Dashboard for proposing agent runs and cloud deployment plans.
- Six specialist roles: product, architecture, implementation, QA, security, and infrastructure.
- AWS, Azure, and Google Cloud deployment-plan previews.
- Explicit production approval policy checks.
- Docker-based local API and GitHub Actions CI.

## Safety boundary

- Agent runs currently generate structured proposals only; they do not execute generated code.
- Cloud adapters are plan-only. No cloud SDKs, credentials, account changes, or apply operations are included.
- Production actions require explicit approval by an authorized human.
- Never commit secrets. Use a managed secret store when provider integrations are added.

## Next milestones

1. Add persistent projects, runs, artifacts, and append-only audit events.
2. Add authentication, RBAC, tenant isolation, and policy administration.
3. Integrate model providers and bounded tool use behind an orchestrator.
4. Add isolated code execution, repository branch/PR workflows, and sandbox quotas.
5. Implement provider-specific infrastructure previews and approval-bound apply workflows.
6. Add enterprise observability, billing/usage controls, and production hardening.
