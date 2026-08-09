"""Deterministic next-action guidance for the Rondo shell menu."""
from __future__ import annotations


def build(
    *,
    repository: str,
    branch: str,
    goal: str = "",
    changed: int = 0,
    knowledge_pending: int = 0,
    jobs: dict[str, int] | None = None,
    test_run: dict | None = None,
    race: dict | None = None,
    proof: dict | None = None,
) -> dict:
    jobs = jobs or {}
    pending_jobs = int(jobs.get("pending", 0))
    active_jobs = int(jobs.get("active", 0))
    test_run = test_run or {}
    test_total = int(test_run.get("total", 0))
    test_complete = min(test_total, int(test_run.get("complete", 0)))
    proof = proof or {}

    if knowledge_pending:
        action, reason = "knowledge", "knowledge_pending"
    elif pending_jobs:
        action, reason = "schedule", "schedule_pending"
    elif test_run and test_complete < test_total:
        action, reason = "test-status", "test_active"
    elif test_run:
        action, reason = "test-finish", "test_complete"
    elif race:
        action, reason = "race-status", "race_active"
    elif changed and not goal:
        action, reason = "goal", "goal_missing"
    elif changed:
        action, reason = "proof", "changes_unverified"
    elif not goal:
        action, reason = "goal", "goal_missing"
    else:
        action, reason = "test", "ready_for_test"

    return {
        "repository": repository,
        "branch": branch or "(detached)",
        "goal": goal,
        "changed": max(0, int(changed)),
        "knowledge_pending": max(0, int(knowledge_pending)),
        "jobs_pending": max(0, pending_jobs),
        "jobs_active": max(0, active_jobs),
        "test": {
            "id": str(test_run.get("id", "")),
            "complete": max(0, test_complete),
            "total": max(0, test_total),
        },
        "race": {
            "id": str((race or {}).get("id", "")),
            "agents": max(0, int((race or {}).get("agents", 0))),
        },
        "proof": {
            "verdict": str(proof.get("verdict", "")),
            "files": max(0, int(proof.get("files", 0))),
        },
        "next": action,
        "reason": reason,
    }
