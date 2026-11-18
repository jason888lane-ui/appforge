from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register_tenant(name: str) -> tuple[str, str]:
    email = f"{name}-{uuid4().hex}@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": name,
            "email": email,
            "password": "a-very-long-test-password",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"], email


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


def test_projects_require_authentication():
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_registration_login_and_tenant_scoped_projects():
    token_a, email_a = register_tenant("Tenant Alpha")
    token_b, _ = register_tenant("Tenant Beta")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email_a, "password": "a-very-long-test-password"},
    )
    assert login.status_code == 200

    created = client.post(
        "/api/v1/projects",
        headers=auth(token_a),
        json={"name": "Private project", "description": "Tenant A data"},
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    assert len(client.get("/api/v1/projects", headers=auth(token_a)).json()) == 1
    assert client.get("/api/v1/projects", headers=auth(token_b)).json() == []

    denied = client.post(
        "/api/v1/agent-runs",
        headers=auth(token_b),
        json={"goal": "Build project agent workflow", "project_id": project_id},
    )
    assert denied.status_code == 404


def test_agent_runs_are_persisted_and_tenant_scoped():
    token, _ = register_tenant("Run Tenant")
    project = client.post(
        "/api/v1/projects", headers=auth(token),
        json={"name": "Agent project"},
    ).json()
    created = client.post(
        "/api/v1/agent-runs",
        headers=auth(token),
        json={"goal": "Create a secure workflow", "project_id": project["id"]},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "proposed"
    assert len(created.json()["tasks"]) == 6
    runs = client.get("/api/v1/runs", headers=auth(token)).json()
    assert any(run["id"] == created.json()["id"] for run in runs)


def test_sandbox_is_disabled_by_default():
    token, _ = register_tenant("Sandbox Tenant")
    project = client.post(
        "/api/v1/projects", headers=auth(token), json={"name": "Sandbox project"}
    ).json()
    response = client.post(
        "/api/v1/sandbox/execute",
        headers=auth(token),
        json={"project_id": project["id"], "source": "print('hello')"},
    )
    assert response.status_code == 503
