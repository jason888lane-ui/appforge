# AppForge architecture

## Design principles

- **Human-governed autonomy:** agents may propose and validate changes; consequential production actions require explicit human approval.
- **Provider-neutral core:** cloud-specific behavior belongs behind adapters, not in the orchestration domain.
- **Isolation by default:** generated code runs in disposable, resource-limited workspaces with no ambient credentials.
- **Traceability:** plans, tool calls, approvals, artifacts, and outcomes become append-only audit events.
- **Incremental delivery:** each milestone must be testable before expanding autonomy.

## Logical components

1. **Web console** — projects, runs, review diffs, policy decisions, usage, and audit history.
2. **API/control plane** — identity, tenant boundaries, project/job lifecycle, policy evaluation.
3. **Orchestrator** — decomposes goals into bounded tasks and coordinates specialized agents.
4. **Agent workers** — repository analysis, implementation, tests, security review, and infrastructure planning.
5. **Execution sandbox** — ephemeral container or microVM per run; restricted network and resource quotas.
6. **Artifact and audit services** — run metadata, logs, diffs, test reports, and approvals.
7. **Provider adapters** — AWS, Azure, Google Cloud, and additional providers; plan first, apply only after approval.

## Initial implementation

The first implementation provides a FastAPI API, draft-only planning endpoint, fail-closed approval policy helper, Docker Compose, and GitHub Actions CI. There is intentionally no code-execution or deployment capability yet.

## Planned data model

Tenant, User, Membership, Project, RepositoryConnection, Run, Task, Artifact, Approval, Policy, AuditEvent, ProviderConnection, Deployment.

All tenant-owned records must carry a tenant identifier and be queried through tenant-scoped repository methods. Authorization must be enforced server-side, not only in the UI.
