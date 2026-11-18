"""Deterministic multi-agent workflow planner.

This is an orchestration foundation, not an LLM integration. Each agent emits
bounded tasks for review; no agent executes shell commands or deploys resources.
"""
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4


class AgentRole(StrEnum):
    PRODUCT = "product"
    ARCHITECT = "architect"
    IMPLEMENTER = "implementer"
    QA = "qa"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"


@dataclass(frozen=True)
class AgentTask:
    task_id: str
    agent: AgentRole
    objective: str
    deliverable: str
    requires_human_review: bool = True


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    goal: str
    tasks: tuple[AgentTask, ...]
    status: str = "proposed"
    execution_started: bool = False


class AgentOrchestrator:
    """Create a role-based plan without invoking external models or tools."""

    def create_run(self, goal: str) -> AgentRun:
        clean_goal = goal.strip()
        if len(clean_goal) < 8:
            raise ValueError("Goal must contain at least 8 characters.")

        definitions = (
            (AgentRole.PRODUCT, "Convert the request into acceptance criteria", "Acceptance criteria"),
            (AgentRole.ARCHITECT, "Design the smallest safe implementation", "Architecture proposal"),
            (AgentRole.IMPLEMENTER, "Prepare an implementation proposal", "Reviewable code change"),
            (AgentRole.QA, "Define and run isolated validation checks", "Test report"),
            (AgentRole.SECURITY, "Review permissions, data boundaries, and risks", "Security review"),
            (AgentRole.INFRASTRUCTURE, "Produce provider-neutral deployment plans", "Infrastructure plan"),
        )
        tasks = tuple(
            AgentTask(
                task_id=str(uuid4()),
                agent=role,
                objective=objective,
                deliverable=deliverable,
            )
            for role, objective, deliverable in definitions
        )
        return AgentRun(run_id=str(uuid4()), goal=clean_goal, tasks=tasks)
