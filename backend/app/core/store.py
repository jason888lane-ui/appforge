"""SQLite persistence with tenant-scoped accessors.

SQLite is the zero-configuration development backend. Set APP_DATABASE_URL to a
sqlite path for local persistence; a PostgreSQL repository can replace this
interface before multi-instance production deployment.
"""
import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

DATABASE_PATH = os.getenv("APP_DATABASE_PATH", "data/appforge.db")


def _connect() -> sqlite3.Connection:
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_store() -> None:
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
                email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
                name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
                project_id TEXT REFERENCES projects(id), goal TEXT NOT NULL,
                status TEXT NOT NULL, tasks_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_runs_tenant ON agent_runs(tenant_id);
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
                actor_id TEXT NOT NULL, event_type TEXT NOT NULL, resource_id TEXT,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id);
            """
        )


def create_tenant_user(name: str, email: str, password_hash: str) -> dict[str, str]:
    tenant_id, user_id = str(uuid4()), str(uuid4())
    with _connect() as db:
        db.execute("INSERT INTO tenants(id, name) VALUES (?, ?)", (tenant_id, name))
        db.execute(
            "INSERT INTO users(id, tenant_id, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, tenant_id, email, password_hash),
        )
    return {"tenant_id": tenant_id, "user_id": user_id, "email": email}


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with _connect() as db:
        return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def create_project(tenant_id: str, name: str, description: str) -> dict[str, Any]:
    project_id = str(uuid4())
    with _connect() as db:
        db.execute(
            "INSERT INTO projects(id, tenant_id, name, description) VALUES (?, ?, ?, ?)",
            (project_id, tenant_id, name, description),
        )
        row = db.execute(
            "SELECT id, name, description, created_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row)


def list_projects(tenant_id: str) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            "SELECT id, name, description, created_at FROM projects "
            "WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def project_belongs_to_tenant(project_id: str, tenant_id: str) -> bool:
    with _connect() as db:
        return db.execute(
            "SELECT 1 FROM projects WHERE id = ? AND tenant_id = ?",
            (project_id, tenant_id),
        ).fetchone() is not None


def save_agent_run(
    tenant_id: str, project_id: str | None, goal: str, tasks: list[dict[str, Any]]
) -> dict[str, Any]:
    run_id = str(uuid4())
    with _connect() as db:
        db.execute(
            "INSERT INTO agent_runs(id, tenant_id, project_id, goal, status, tasks_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, tenant_id, project_id, goal, "proposed", json.dumps(tasks)),
        )
        db.execute(
            "INSERT INTO audit_events(id, tenant_id, actor_id, event_type, resource_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), tenant_id, "system", "agent_run.proposed", run_id),
        )
    return {"id": run_id, "project_id": project_id, "goal": goal, "status": "proposed", "tasks": tasks}


def list_agent_runs(tenant_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
    query = (
        "SELECT id, project_id, goal, status, tasks_json, created_at "
        "FROM agent_runs WHERE tenant_id = ?"
    )
    params: list[str] = [tenant_id]
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    query += " ORDER BY created_at DESC"
    with _connect() as db:
        rows = db.execute(query, params).fetchall()
    return [
        {
            "id": row["id"], "project_id": row["project_id"], "goal": row["goal"],
            "status": row["status"], "tasks": json.loads(row["tasks_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def record_audit(
    tenant_id: str, actor_id: str, event_type: str, resource_id: str | None, details: dict[str, Any]
) -> None:
    with _connect() as db:
        db.execute(
            "INSERT INTO audit_events(id, tenant_id, actor_id, event_type, resource_id, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), tenant_id, actor_id, event_type, resource_id, json.dumps(details)),
        )
