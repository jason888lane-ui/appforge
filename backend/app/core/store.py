"""Tenant-scoped SQL persistence for SQLite development and PostgreSQL deployments."""
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/appforge.db")


def _make_engine() -> Engine:
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.removeprefix("sqlite:///")
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True)
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


engine = _make_engine()


def initialize_store() -> None:
    ddl = [
        """CREATE TABLE IF NOT EXISTS tenants (
            id VARCHAR(36) PRIMARY KEY, name VARCHAR(120) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
            email VARCHAR(254) NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role VARCHAR(24) NOT NULL DEFAULT 'developer',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS projects (
            id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
            name VARCHAR(120) NOT NULL, description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS agent_runs (
            id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
            project_id VARCHAR(36) REFERENCES projects(id), goal TEXT NOT NULL,
            status VARCHAR(32) NOT NULL, tasks_json TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS audit_events (
            id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
            actor_id VARCHAR(36) NOT NULL, event_type VARCHAR(120) NOT NULL, resource_id VARCHAR(36),
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        "CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_runs_tenant ON agent_runs(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id)",
        """CREATE TABLE IF NOT EXISTS agent_jobs (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
            project_id VARCHAR(36) REFERENCES projects(id),
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            goal TEXT NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            locked_by VARCHAR(120),
            locked_at TIMESTAMP,
            last_error TEXT,
            result_run_id VARCHAR(36) REFERENCES agent_runs(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        "CREATE INDEX IF NOT EXISTS idx_agent_jobs_tenant ON agent_jobs(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_agent_jobs_status_created ON agent_jobs(status, created_at)",
    ]
    with engine.begin() as db:
        for statement in ddl:
            db.execute(text(statement))
        columns = db.execute(text("SELECT * FROM users WHERE 1=0")).keys()
        if "role" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(24) NOT NULL DEFAULT 'developer'"))


def create_tenant_user(name: str, email: str, password_hash: str) -> dict[str, str]:
    tenant_id, user_id = str(uuid4()), str(uuid4())
    with engine.begin() as db:
        db.execute(text("INSERT INTO tenants(id, name) VALUES (:id, :name)"),
                   {"id": tenant_id, "name": name})
        db.execute(text(
            "INSERT INTO users(id, tenant_id, email, password_hash, role) "
            "VALUES (:id, :tenant, :email, :password, 'owner')"
        ), {"id": user_id, "tenant": tenant_id, "email": email, "password": password_hash})
    return {"tenant_id": tenant_id, "user_id": user_id, "email": email, "role": "owner"}


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with engine.connect() as db:
        row = db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().first()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with engine.connect() as db:
        row = db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email}).mappings().first()
    return dict(row) if row else None


def create_tenant_member(tenant_id: str, email: str, password_hash: str, role: str) -> dict[str, str]:
    user_id = str(uuid4())
    with engine.begin() as db:
        db.execute(text(
            "INSERT INTO users(id, tenant_id, email, password_hash, role) "
            "VALUES (:id, :tenant, :email, :password, :role)"
        ), {"id": user_id, "tenant": tenant_id, "email": email,
            "password": password_hash, "role": role})
    return {"user_id": user_id, "tenant_id": tenant_id, "email": email, "role": role}


def create_project(tenant_id: str, name: str, description: str) -> dict[str, Any]:
    project_id = str(uuid4())
    with engine.begin() as db:
        db.execute(text(
            "INSERT INTO projects(id, tenant_id, name, description) VALUES (:id, :tenant, :name, :description)"
        ), {"id": project_id, "tenant": tenant_id, "name": name, "description": description})
        row = db.execute(text(
            "SELECT id, name, description, created_at FROM projects WHERE id = :id"
        ), {"id": project_id}).mappings().one()
    return dict(row)


def list_projects(tenant_id: str) -> list[dict[str, Any]]:
    with engine.connect() as db:
        rows = db.execute(text(
            "SELECT id, name, description, created_at FROM projects "
            "WHERE tenant_id = :tenant ORDER BY created_at DESC"
        ), {"tenant": tenant_id}).mappings().all()
    return [dict(row) for row in rows]


def project_belongs_to_tenant(project_id: str, tenant_id: str) -> bool:
    with engine.connect() as db:
        return db.execute(text(
            "SELECT 1 FROM projects WHERE id = :id AND tenant_id = :tenant"
        ), {"id": project_id, "tenant": tenant_id}).first() is not None


def save_agent_run(tenant_id: str, project_id: str | None, goal: str,
                   tasks: list[dict[str, Any]]) -> dict[str, Any]:
    run_id = str(uuid4())
    with engine.begin() as db:
        db.execute(text(
            "INSERT INTO agent_runs(id, tenant_id, project_id, goal, status, tasks_json) "
            "VALUES (:id, :tenant, :project, :goal, 'proposed', :tasks)"
        ), {"id": run_id, "tenant": tenant_id, "project": project_id,
            "goal": goal, "tasks": json.dumps(tasks)})
        db.execute(text(
            "INSERT INTO audit_events(id, tenant_id, actor_id, event_type, resource_id) "
            "VALUES (:id, :tenant, 'system', 'agent_run.proposed', :resource)"
        ), {"id": str(uuid4()), "tenant": tenant_id, "resource": run_id})
    return {"id": run_id, "project_id": project_id, "goal": goal, "status": "proposed", "tasks": tasks}


def list_agent_runs(tenant_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
    query = ("SELECT id, project_id, goal, status, tasks_json, created_at "
             "FROM agent_runs WHERE tenant_id = :tenant")
    params: dict[str, Any] = {"tenant": tenant_id}
    if project_id:
        query += " AND project_id = :project"
        params["project"] = project_id
    query += " ORDER BY created_at DESC"
    with engine.connect() as db:
        rows = db.execute(text(query), params).mappings().all()
    return [{"id": row["id"], "project_id": row["project_id"], "goal": row["goal"],
             "status": row["status"], "tasks": json.loads(row["tasks_json"]),
             "created_at": row["created_at"]} for row in rows]


def record_audit(tenant_id: str, actor_id: str, event_type: str,
                 resource_id: str | None, details: dict[str, Any]) -> None:
    with engine.begin() as db:
        db.execute(text(
            "INSERT INTO audit_events(id, tenant_id, actor_id, event_type, resource_id, details_json) "
            "VALUES (:id, :tenant, :actor, :event, :resource, :details)"
        ), {"id": str(uuid4()), "tenant": tenant_id, "actor": actor_id,
            "event": event_type, "resource": resource_id, "details": json.dumps(details)})



def enqueue_agent_job(
    tenant_id: str, created_by: str, project_id: str | None, goal: str
) -> dict[str, Any]:
    job_id = str(uuid4())
    with engine.begin() as db:
        db.execute(text(
            "INSERT INTO agent_jobs(id, tenant_id, project_id, created_by, goal) "
            "VALUES (:id, :tenant, :project, :actor, :goal)"
        ), {
            "id": job_id, "tenant": tenant_id, "project": project_id,
            "actor": created_by, "goal": goal,
        })
        db.execute(text(
            "INSERT INTO audit_events(id, tenant_id, actor_id, event_type, resource_id, details_json) "
            "VALUES (:id, :tenant, :actor, 'agent_job.queued', :resource, :details)"
        ), {
            "id": str(uuid4()), "tenant": tenant_id, "actor": created_by,
            "resource": job_id, "details": json.dumps({"project_id": project_id}),
        })
    return {
        "id": job_id, "project_id": project_id, "goal": goal,
        "status": "queued", "attempts": 0,
    }


def get_agent_job(tenant_id: str, job_id: str) -> dict[str, Any] | None:
    with engine.connect() as db:
        row = db.execute(text(
            "SELECT id, project_id, goal, status, attempts, max_attempts, "
            "last_error, result_run_id, created_at, updated_at "
            "FROM agent_jobs WHERE id = :id AND tenant_id = :tenant"
        ), {"id": job_id, "tenant": tenant_id}).mappings().first()
    return dict(row) if row else None


def claim_next_agent_job(worker_id: str, lease_seconds: int = 300) -> dict[str, Any] | None:
    stale_before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=lease_seconds)
    with engine.begin() as db:
        db.execute(text(
            "UPDATE agent_jobs SET status = 'failed', locked_by = NULL, locked_at = NULL, "
            "last_error = 'Worker lease expired after maximum attempts', updated_at = CURRENT_TIMESTAMP "
            "WHERE status = 'running' AND attempts >= max_attempts AND locked_at < :stale_before"
        ), {"stale_before": stale_before})
        row = db.execute(text(
            "UPDATE agent_jobs SET status = 'running', attempts = attempts + 1, "
            "locked_by = :worker, locked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = (SELECT id FROM agent_jobs WHERE attempts < max_attempts AND "
            "(status = 'queued' OR (status = 'running' AND locked_at < :stale_before)) "
            "ORDER BY created_at LIMIT 1) AND attempts < max_attempts AND "
            "(status = 'queued' OR (status = 'running' AND locked_at < :stale_before)) "
            "RETURNING id, tenant_id, project_id, created_by, goal, attempts, max_attempts"
        ), {"worker": worker_id, "stale_before": stale_before}).mappings().first()
    return dict(row) if row else None


def complete_agent_job(job_id: str, worker_id: str, run_id: str) -> bool:
    with engine.begin() as db:
        result = db.execute(text(
            "UPDATE agent_jobs SET status = 'completed', result_run_id = :run, "
            "locked_by = NULL, locked_at = NULL, last_error = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :id AND status = 'running' AND locked_by = :worker"
        ), {"id": job_id, "worker": worker_id, "run": run_id})
    return result.rowcount == 1


def fail_agent_job(job_id: str, worker_id: str, error: str) -> bool:
    safe_error = error[:1000]
    with engine.begin() as db:
        result = db.execute(text(
            "UPDATE agent_jobs SET status = CASE WHEN attempts >= max_attempts "
            "THEN 'failed' ELSE 'queued' END, locked_by = NULL, locked_at = NULL, "
            "last_error = :error, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :id AND status = 'running' AND locked_by = :worker"
        ), {"id": job_id, "worker": worker_id, "error": safe_error})
    return result.rowcount == 1
