from uuid import uuid4

from app.main import app
from app.worker import process_one
from fastapi.testclient import TestClient

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
    assert "APP<span>FORGE</span>" in response.text


def test_plan_is_draft_and_never_executes():
    token, _ = register_tenant("Plan Tenant")
    response = client.post(
        "/api/v1/plans", headers=auth(token),
        json={"goal": "Create a secure customer portal", "target_environment": "production"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["execution_started"] is False
    assert len(body["steps"]) >= 3


def test_production_approval_fails_closed():
    token, _ = register_tenant("Approval Tenant")
    response = client.post(
        "/api/v1/approvals/check", headers=auth(token),
        json={"target_environment": "production", "human_approved": False},
    )
    assert response.json()["allowed"] is False
    assert response.json()["execution_started"] is False


def test_approval_requires_owner_authentication():
    response = client.post(
        "/api/v1/approvals/check",
        json={"target_environment": "production", "human_approved": True},
    )
    assert response.status_code == 401


def test_authenticated_owner_is_recorded_as_approver():
    token, _ = register_tenant("Named Approver Tenant")
    response = client.post(
        "/api/v1/approvals/check", headers=auth(token),
        json={"target_environment": "production", "human_approved": True},
    )
    assert response.json()["allowed"] is True
    assert response.json()["approver_id"]
    assert response.json()["execution_started"] is False


def test_agent_run_returns_six_roles_and_does_not_execute():
    token, _ = register_tenant("Agent Tenant")
    response = client.post(
        "/api/v1/agents/runs", headers=auth(token),
        json={"goal": "Build a secure internal developer portal"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["agents"]) == 6
    assert body["execution_started"] is False


def test_cloud_plan_is_preview_only():
    token, _ = register_tenant("Cloud Tenant")
    response = client.post(
        "/api/v1/cloud/plan", headers=auth(token),
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



def test_owner_can_add_viewer_and_viewer_cannot_write():
    owner_token, _ = register_tenant("RBAC Tenant")
    created = client.post(
        "/api/v1/team/members",
        headers=auth(owner_token),
        json={
            "email": f"viewer-{uuid4().hex}@example.test",
            "temporary_password": "temporary-password-123",
            "role": "viewer",
        },
    )
    assert created.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": created.json()["email"],
            "password": "temporary-password-123",
        },
    )
    assert login.status_code == 200
    viewer_token = login.json()["access_token"]
    assert client.get("/api/v1/projects", headers=auth(viewer_token)).status_code == 200
    denied = client.post(
        "/api/v1/projects",
        headers=auth(viewer_token),
        json={"name": "Viewer cannot create"},
    )
    assert denied.status_code == 403


def test_non_owner_cannot_provision_team_members():
    owner_token, _ = register_tenant("Member Tenant")
    viewer = client.post(
        "/api/v1/team/members",
        headers=auth(owner_token),
        json={
            "email": f"viewer-{uuid4().hex}@example.test",
            "temporary_password": "temporary-password-123",
            "role": "viewer",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": viewer.json()["email"], "password": "temporary-password-123"},
    )
    denied = client.post(
        "/api/v1/team/members",
        headers=auth(login.json()["access_token"]),
        json={
            "email": f"second-{uuid4().hex}@example.test",
            "temporary_password": "temporary-password-456",
            "role": "developer",
        },
    )
    assert denied.status_code == 403



def test_legacy_agent_and_cloud_planner_endpoints_require_authentication():
    agent = client.post(
        "/api/v1/agents/runs",
        json={"goal": "Build a secure internal developer portal"},
    )
    cloud = client.post(
        "/api/v1/cloud/plan",
        json={"provider": "aws", "environment": "staging", "region": "us-east-1"},
    )
    plan = client.post(
        "/api/v1/plans",
        json={"goal": "Create a secure customer portal"},
    )
    assert agent.status_code == 401
    assert cloud.status_code == 401
    assert plan.status_code == 401


def test_viewer_cannot_check_production_approval():
    owner_token, _ = register_tenant("Viewer Approval Tenant")
    member = client.post(
        "/api/v1/team/members",
        headers=auth(owner_token),
        json={
            "email": f"viewer-{uuid4().hex}@example.test",
            "temporary_password": "temporary-password-123",
            "role": "viewer",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": member.json()["email"], "password": "temporary-password-123"},
    )
    denied = client.post(
        "/api/v1/approvals/check",
        headers=auth(login.json()["access_token"]),
        json={"target_environment": "production", "human_approved": True},
    )
    assert denied.status_code == 403



def test_agent_job_queue_is_tenant_scoped():
    token_a, _ = register_tenant("Queue Tenant A")
    token_b, _ = register_tenant("Queue Tenant B")
    queued = client.post(
        "/api/v1/agent-jobs",
        headers=auth(token_a),
        json={"goal": "Create a queued agent workflow"},
    )
    assert queued.status_code == 200
    job_id = queued.json()["id"]
    assert queued.json()["status"] == "queued"
    assert client.get(
        f"/api/v1/agent-jobs/{job_id}", headers=auth(token_a)
    ).status_code == 200
    assert client.get(
        f"/api/v1/agent-jobs/{job_id}", headers=auth(token_b)
    ).status_code == 404


def test_background_worker_completes_proposal_without_executing_code():
    token, _ = register_tenant("Worker Tenant")
    queued = client.post(
        "/api/v1/agent-jobs",
        headers=auth(token),
        json={"goal": "Create a reviewable agent proposal"},
    ).json()
    assert process_one("test-worker") is True
    job = client.get(
        f"/api/v1/agent-jobs/{queued['id']}", headers=auth(token)
    ).json()
    assert job["status"] == "completed"
    assert job["result_run_id"]
    runs = client.get("/api/v1/runs", headers=auth(token)).json()
    assert any(run["id"] == job["result_run_id"] for run in runs)
    assert all(task["requires_human_review"] for run in runs for task in run["tasks"])


def test_background_worker_returns_false_when_queue_is_empty():
    assert process_one("idle-test-worker") is False
