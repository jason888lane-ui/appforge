"""AppForge API: tenant-aware project storage and guarded AI/sandbox services."""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.agents.orchestrator import AgentOrchestrator
from app.cloud.adapters import CloudProvider, create_deployment_plan
from app.core import store
from app.core.approval import evaluate_production_approval
from app.core.auth import (
    Principal,
    hash_password,
    issue_token,
    require_roles,
    verify_password,
)
from app.providers.models import ModelProviderError, configured_provider
from app.sandbox.docker_runner import SandboxUnavailable, execute_python

app = FastAPI(
    title="AppForge API",
    description="Tenant-aware, human-governed autonomous development platform.",
    version="0.3.0",
)
orchestrator = AgentOrchestrator()
DASHBOARD = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
store.initialize_store()
owner_dependency = Depends(require_roles("owner"))
editor_dependency = Depends(require_roles("owner", "developer"))
member_dependency = Depends(require_roles("owner", "developer", "viewer"))


class PlanRequest(BaseModel):
    goal: str = Field(min_length=8, max_length=4000)
    target_environment: str = Field(
        default="development", pattern="^(development|staging|production)$"
    )


class PlanResponse(BaseModel):
    status: str
    goal: str
    target_environment: str
    steps: list[str]
    execution_started: bool = False


class ApprovalCheckRequest(BaseModel):
    target_environment: str = Field(pattern="^(development|staging|production)$")
    human_approved: bool = False


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=8, max_length=4000)
    project_id: str | None = None


class CloudPlanRequest(BaseModel):
    provider: CloudProvider
    environment: str = Field(pattern="^(development|staging|production)$")
    region: str = Field(min_length=2, max_length=80)


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class TeamMemberRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    temporary_password: str = Field(min_length=12, max_length=128)
    role: str = Field(pattern="^(developer|viewer)$")


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)


class ModelRequest(BaseModel):
    provider: str = Field(pattern="^(openai|anthropic)$")
    prompt: str = Field(min_length=1, max_length=12000)


class SandboxRequest(BaseModel):
    project_id: str
    source: str = Field(min_length=1, max_length=32000)
    timeout_seconds: int = Field(default=15, ge=1, le=20)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "appforge-api"}


@app.get("/api/v1/status", tags=["operations"])
def status() -> dict[str, str]:
    return {
        "name": "AppForge",
        "stage": "tenant-storage-and-provider-foundation",
        "authentication": "enabled",
        "model_execution": "requires-provider-credentials",
        "sandbox_execution": "opt-in-docker-only",
        "cloud_apply": "disabled",
    }


@app.post("/api/v1/auth/register", tags=["authentication"])
def register(request: RegisterRequest) -> dict[str, str]:
    email = request.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    try:
        user = store.create_tenant_user(
            request.tenant_name.strip(), email, hash_password(request.password)
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with that email already exists") from exc
    return {"access_token": issue_token(user), "token_type": "bearer", "tenant_id": user["tenant_id"]}


@app.post("/api/v1/auth/login", tags=["authentication"])
def login(request: LoginRequest) -> dict[str, str]:
    user = store.get_user_by_email(request.email.strip().lower())
    if user is None or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    identity = {"user_id": user["id"], "tenant_id": user["tenant_id"], "email": user["email"], "role": user["role"]}
    return {"access_token": issue_token(identity), "token_type": "bearer"}


@app.post("/api/v1/team/members", tags=["team"])
def add_team_member(
    request: TeamMemberRequest, principal: Principal = owner_dependency
) -> dict[str, str]:
    email = request.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    try:
        member = store.create_tenant_member(
            principal.tenant_id, email, hash_password(request.temporary_password), request.role
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with that email already exists") from exc
    store.record_audit(
        principal.tenant_id, principal.user_id, "team.member_created",
        member["user_id"], {"role": request.role},
    )
    return {"user_id": member["user_id"], "email": member["email"], "role": member["role"]}


@app.get("/api/v1/auth/me", tags=["authentication"])
def who_am_i(principal: Principal = member_dependency) -> dict[str, str]:
    return {
        "user_id": principal.user_id, "tenant_id": principal.tenant_id,
        "email": principal.email, "role": principal.role,
    }


@app.post("/api/v1/projects", tags=["projects"])
def create_project(
    request: ProjectRequest, principal: Principal = editor_dependency
) -> dict[str, object]:
    return store.create_project(principal.tenant_id, request.name, request.description)


@app.get("/api/v1/projects", tags=["projects"])
def get_projects(principal: Principal = member_dependency) -> list[dict[str, object]]:
    return store.list_projects(principal.tenant_id)


@app.get("/api/v1/runs", tags=["agents"])
def get_runs(principal: Principal = member_dependency) -> list[dict[str, object]]:
    return store.list_agent_runs(principal.tenant_id)


@app.post("/api/v1/agent-runs", tags=["agents"])
def create_persistent_agent_run(
    request: AgentRunRequest, principal: Principal = editor_dependency
) -> dict[str, object]:
    if request.project_id and not store.project_belongs_to_tenant(
        request.project_id, principal.tenant_id
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    proposed = orchestrator.create_run(request.goal)
    tasks = [
        {
            "task_id": task.task_id, "agent": task.agent.value,
            "objective": task.objective, "deliverable": task.deliverable,
            "requires_human_review": task.requires_human_review,
        }
        for task in proposed.tasks
    ]
    return store.save_agent_run(principal.tenant_id, request.project_id, request.goal, tasks)


@app.post("/api/v1/agent-jobs", tags=["agents"])
def enqueue_agent_proposal(
    request: AgentRunRequest, principal: Principal = editor_dependency
) -> dict[str, object]:
    if request.project_id and not store.project_belongs_to_tenant(
        request.project_id, principal.tenant_id
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    return store.enqueue_agent_job(
        principal.tenant_id, principal.user_id, request.project_id, request.goal
    )


@app.get("/api/v1/agent-jobs/{job_id}", tags=["agents"])
def get_agent_job_status(
    job_id: str, principal: Principal = member_dependency
) -> dict[str, object]:
    job = store.get_agent_job(principal.tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    return job


@app.post("/api/v1/models/complete", tags=["models"])
async def complete_with_model(
    request: ModelRequest, principal: Principal = editor_dependency
) -> dict[str, str]:
    try:
        answer = await configured_provider(request.provider).complete(request.prompt)
    except ModelProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    store.record_audit(
        principal.tenant_id, principal.user_id, "model.completion", None,
        {"provider": request.provider},
    )
    return {"provider": request.provider, "response": answer}


@app.post("/api/v1/sandbox/execute", tags=["sandbox"])
def run_in_sandbox(
    request: SandboxRequest, principal: Principal = owner_dependency
) -> dict[str, object]:
    if not store.project_belongs_to_tenant(request.project_id, principal.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = execute_python(request.source, request.timeout_seconds)
    except SandboxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.record_audit(
        principal.tenant_id, principal.user_id, "sandbox.execution",
        request.project_id, {"status": result["status"]},
    )
    return result


@app.post("/api/v1/plans", response_model=PlanResponse, tags=["planning"])
def create_plan(
    request: PlanRequest, principal: Principal = member_dependency
) -> PlanResponse:
    steps = [
        "Clarify acceptance criteria and constraints",
        "Inspect the target repository and identify affected components",
        "Propose a minimal implementation and test strategy",
        "Run static analysis and automated tests in an isolated workspace",
        "Prepare a reviewable change set for human approval",
    ]
    return PlanResponse(
        status="draft", goal=request.goal, target_environment=request.target_environment,
        steps=steps, execution_started=False,
    )


@app.post("/api/v1/agents/runs", tags=["agents"])
def create_agent_run(
    request: AgentRunRequest, principal: Principal = editor_dependency
) -> dict[str, object]:
    run = orchestrator.create_run(request.goal)
    return {
        "run_id": run.run_id, "goal": run.goal, "status": run.status,
        "execution_started": run.execution_started,
        "agents": [
            {
                "task_id": task.task_id, "agent": task.agent.value,
                "objective": task.objective, "deliverable": task.deliverable,
                "requires_human_review": task.requires_human_review,
            }
            for task in run.tasks
        ],
    }


@app.post("/api/v1/cloud/plan", tags=["cloud"])
def cloud_plan(
    request: CloudPlanRequest, principal: Principal = member_dependency
) -> dict[str, object]:
    try:
        plan = create_deployment_plan(
            provider=request.provider, environment=request.environment, region=request.region
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "provider": plan.provider.value, "environment": plan.environment,
        "region": plan.region, "proposed_services": list(plan.proposed_services),
        "actions": list(plan.actions), "apply_enabled": plan.apply_enabled,
    }


@app.post("/api/v1/approvals/check", tags=["governance"])
def check_approval(
    request: ApprovalCheckRequest, principal: Principal = owner_dependency
) -> dict[str, object]:
    # The approver identity comes from the authenticated owner, never caller input.
    decision = evaluate_production_approval(
        environment=request.target_environment, human_approved=request.human_approved,
        approver_id=principal.user_id if request.human_approved else None,
    )
    store.record_audit(
        principal.tenant_id, principal.user_id, "governance.approval_checked", None,
        {
            "environment": request.target_environment,
            "human_approved": request.human_approved,
            "allowed": decision.allowed,
        },
    )
    return {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "approver_id": principal.user_id if request.human_approved else None,
        "execution_started": False,
    }
