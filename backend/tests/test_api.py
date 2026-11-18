from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
