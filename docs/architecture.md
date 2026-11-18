# AppForge architecture

## Design principles

- **Human-governed autonomy:** agents may propose and validate changes; consequential production actions require explicit human approval.
- **Provider-neutral core:** cloud-specific behavior belongs behind adapters, not in the orchestration domain.
- **Isolation by default:** generated code runs in disposable, resource-limited workspaces with no ambient credentials.
- **Traceability:** plans, tool calls, approvals, artifacts, and outcomes become append-only audit events.
- **Incremental delivery:** each milestone must be testable before expanding autonomy.

## Current implementation

- FastAPI control-plane API with a browser dashboard.
- Deterministic six-role planning workflow: product, architect, implementation, QA, security, infrastructure.
- AWS, Azure, and Google Cloud plan-only adapters. They return proposed service categories and safety steps; they do not inspect accounts or provision resources.
- Approval-policy helper that fails closed for production when approval or approver identity is missing.
- Docker Compose development environment and GitHub Actions CI.

The current agent workflow is a deterministic orchestration scaffold, not an LLM-powered autonomous coding system. No generated code is executed.

## Logical target architecture

1. **Web console** — projects, runs, review diffs, policy decisions, usage, and audit history.
2. **API/control plane** — identity, tenant boundaries, project/job lifecycle, policy evaluation.
3. **Orchestrator** — decomposes goals into bounded tasks and coordinates specialized agents.
4. **Agent workers** — repository analysis, implementation, tests, security review, and infrastructure planning.
5. **Execution sandbox** — ephemeral container or microVM per run; restricted network and resource quotas.
6. **Artifact and audit services** — run metadata, logs, diffs, test reports, and approvals.
7. **Provider adapters** — AWS, Azure, Google Cloud, and additional providers; plan first, apply only after approval.

## Planned data model

Tenant, User, Membership, Project, RepositoryConnection, Run, Task, Artifact, Approval, Policy, AuditEvent, ProviderConnection, Deployment.

All tenant-owned records must carry a tenant identifier and be queried through tenant-scoped repository methods. Authorization must be enforced server-side, not only in the UI.
