"""AppForge API foundation."""
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.core.approval import evaluate_production_approval

app = FastAPI(
    title="AppForge API",
    description="Foundation API for a human-governed autonomous development platform.",
    version="0.1.0",
)


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


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "appforge-api"}


@app.get("/api/v1/status", tags=["operations"])
def status() -> dict[str, str]:
    return {"name": "AppForge", "stage": "foundation", "execution": "disabled"}


@app.post("/api/v1/plans", response_model=PlanResponse, tags=["planning"])
def create_plan(request: PlanRequest) -> PlanResponse:
    """Return a starter plan; generated code is never run by this endpoint."""
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


@app.post("/api/v1/approvals/check", tags=["governance"])
def check_approval(request: ApprovalCheckRequest) -> dict[str, object]:
    decision = evaluate_production_approval(
        environment=request.target_environment,
        human_approved=request.human_approved,
        approver_id=request.approver_id,
    )
    return {"allowed": decision.allowed, "reason": decision.reason}
