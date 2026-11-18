"""AppForge API foundation."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import AgentOrchestrator
from app.cloud.adapters import CloudProvider, create_deployment_plan
from app.core.approval import evaluate_production_approval

app = FastAPI(
    title="AppForge API",
    description="Foundation API for a human-governed autonomous development platform.",
    version="0.2.0",
)
orchestrator = AgentOrchestrator()
DASHBOARD = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


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
    approver_id: str | None = None


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=8, max_length=4000)


class CloudPlanRequest(BaseModel):
    provider: CloudProvider
    environment: str = Field(pattern="^(development|staging|production)$")
    region: str = Field(min_length=2, max_length=80)


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
        "stage": "multi-agent-foundation",
        "execution": "disabled",
        "cloud_apply": "disabled",
    }


@app.post("/api/v1/plans", response_model=PlanResponse, tags=["planning"])
def create_plan(request: PlanRequest) -> PlanResponse:
    steps = [
        "Clarify acceptance criteria and constraints",
        "Inspect the target repository and identify affected components",
        "Propose a minimal implementation and test strategy",
        "Run static analysis and automated tests in an isolated workspace",
        "Prepare a reviewable change set for human approval",
    ]
    return PlanResponse(
        status="draft",
        goal=request.goal,
        target_environment=request.target_environment,
        steps=steps,
        execution_started=False,
    )


@app.post("/api/v1/agents/runs", tags=["agents"])
def create_agent_run(request: AgentRunRequest) -> dict[str, object]:
    run = orchestrator.create_run(request.goal)
    return {
        "run_id": run.run_id,
        "goal": run.goal,
        "status": run.status,
        "execution_started": run.execution_started,
        "agents": [
            {
                "task_id": task.task_id,
                "agent": task.agent.value,
                "objective": task.objective,
                "deliverable": task.deliverable,
                "requires_human_review": task.requires_human_review,
            }
            for task in run.tasks
        ],
    }


@app.post("/api/v1/cloud/plan", tags=["cloud"])
def cloud_plan(request: CloudPlanRequest) -> dict[str, object]:
    try:
        plan = create_deployment_plan(
            provider=request.provider,
            environment=request.environment,
            region=request.region,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "provider": plan.provider.value,
        "environment": plan.environment,
        "region": plan.region,
        "proposed_services": list(plan.proposed_services),
        "actions": list(plan.actions),
        "apply_enabled": plan.apply_enabled,
    }


@app.post("/api/v1/approvals/check", tags=["governance"])
def check_approval(request: ApprovalCheckRequest) -> dict[str, object]:
    decision = evaluate_production_approval(
        environment=request.target_environment,
        human_approved=request.human_approved,
        approver_id=request.approver_id,
    )
    return {"allowed": decision.allowed, "reason": decision.reason}
