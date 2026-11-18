from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "APPFORGE" in response.text


def test_plan_is_draft_and_never_executes():
    response = client.post(
        "/api/v1/plans",
        json={"goal": "Create a secure customer portal", "target_environment": "production"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["execution_started"] is False
    assert len(body["steps"]) >= 3


def test_production_approval_fails_closed():
    response = client.post(
        "/api/v1/approvals/check",
        json={"target_environment": "production", "human_approved": False},
    )
    assert response.json()["allowed"] is False


def test_production_requires_named_approver():
    response = client.post(
        "/api/v1/approvals/check",
        json={"target_environment": "production", "human_approved": True},
    )
    assert response.json()["allowed"] is False


def test_named_human_approval_passes_policy_check():
    response = client.post(
        "/api/v1/approvals/check",
        json={
            "target_environment": "production",
            "human_approved": True,
            "approver_id": "operator-123",
        },
    )
    assert response.json()["allowed"] is True


def test_agent_run_returns_six_roles_and_does_not_execute():
    response = client.post(
        "/api/v1/agents/runs", json={"goal": "Build a secure internal developer portal"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["agents"]) == 6
    assert body["execution_started"] is False


def test_cloud_plan_is_preview_only():
    response = client.post(
        "/api/v1/cloud/plan",
        json={"provider": "aws", "environment": "staging", "region": "us-east-1"},
    )
    assert response.status_code == 200
    assert response.json()["apply_enabled"] is False
