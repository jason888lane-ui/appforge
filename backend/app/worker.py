"""Durable worker for deterministic, review-only agent proposal jobs.

This worker does not call LLMs, execute generated code, or deploy infrastructure.
"""
import logging
import os
import time
from uuid import uuid4

from app.agents.orchestrator import AgentOrchestrator
from app.core import store

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("appforge.worker")
orchestrator = AgentOrchestrator()


def process_one(worker_id: str) -> bool:
    """Claim and process one queued proposal. Returns False when queue is empty."""
    job = store.claim_next_agent_job(worker_id)
    if job is None:
        return False

    try:
        proposed = orchestrator.create_run(job["goal"])
        tasks = [
            {
                "task_id": task.task_id,
                "agent": task.agent.value,
                "objective": task.objective,
                "deliverable": task.deliverable,
                "requires_human_review": task.requires_human_review,
            }
            for task in proposed.tasks
        ]
        run = store.save_agent_run(
            job["tenant_id"], job["project_id"], job["goal"], tasks
        )
        if not store.complete_agent_job(job["id"], worker_id, run["id"]):
            raise RuntimeError("Job lease was lost before completion could be recorded")
        store.record_audit(
            job["tenant_id"], job["created_by"], "agent_job.completed",
            job["id"], {"run_id": run["id"], "worker_id": worker_id},
        )
        logger.info("Completed agent job %s as run %s", job["id"], run["id"])
    except Exception as exc:
        store.fail_agent_job(job["id"], worker_id, str(exc))
        logger.exception("Agent job %s failed", job["id"])
    return True


def main() -> None:
    store.initialize_store()
    worker_id = os.getenv("APPFORGE_WORKER_ID", f"worker-{uuid4()}")
    poll_seconds = max(1, int(os.getenv("APPFORGE_WORKER_POLL_SECONDS", "2")))
    logger.info("AppForge worker %s started", worker_id)
    while True:
        if not process_one(worker_id):
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
