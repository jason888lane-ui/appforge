"""Fail-closed approval policy for consequential operations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalDecision:
    allowed: bool
    reason: str


def evaluate_production_approval(
    *, environment: str, human_approved: bool, approver_id: str | None
) -> ApprovalDecision:
    """Evaluate approval only; this function never executes a deployment."""
    if environment.lower() != "production":
        return ApprovalDecision(True, "Non-production operation.")
    if not human_approved:
        return ApprovalDecision(False, "Production requires explicit human approval.")
    if not approver_id or not approver_id.strip():
        return ApprovalDecision(False, "Production approval must identify the approver.")
    return ApprovalDecision(True, "Explicit human approval supplied.")
