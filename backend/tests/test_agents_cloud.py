from app.agents.orchestrator import AgentOrchestrator, AgentRole
from app.cloud.adapters import CloudProvider, create_deployment_plan
import pytest


def test_orchestrator_proposes_six_specialist_tasks_without_execution():
    run = AgentOrchestrator().create_run("Build a secure internal developer portal")
    assert len(run.tasks) == 6
    assert {task.agent for task in run.tasks} == set(AgentRole)
    assert run.status == "proposed"
    assert run.execution_started is False
    assert all(task.requires_human_review for task in run.tasks)


def test_orchestrator_rejects_empty_goal():
    with pytest.raises(ValueError):
        AgentOrchestrator().create_run("  ")


@pytest.mark.parametrize("provider", list(CloudProvider))
def test_cloud_adapters_are_plan_only(provider):
    plan = create_deployment_plan(
        provider=provider, environment="staging", region="test-region"
    )
    assert plan.provider == provider
    assert plan.apply_enabled is False
    assert any("human approval" in action for action in plan.actions)


def test_cloud_adapter_rejects_invalid_environment():
    with pytest.raises(ValueError):
        create_deployment_plan(
            provider=CloudProvider.AWS, environment="prod-ish", region="us-east-1"
        )
