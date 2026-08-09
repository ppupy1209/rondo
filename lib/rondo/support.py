"""Privacy-preserving support bundles with an explicit metadata allowlist."""
from __future__ import annotations

import json
import os
import platform
import time
import zipfile
from pathlib import Path

from .paths import repo_key


class SupportError(RuntimeError):
    pass


def report(
    *,
    version: str,
    root: Path,
    branch: str,
    config: dict[str, str],
    agents: dict[str, bool],
    state: dict,
    installation: dict,
) -> dict:
    def allowed(name: str, choices: set[str]) -> str:
        value = str(config.get(name, ""))
        return value if value in choices else "invalid"

    agent_names = {"claude", "codex", "gemini", "kimi", "grok"}
    panels = str(config.get("panels", "")).replace(",", " ").split()
    panels = list(dict.fromkeys(name for name in panels if name in agent_names))[:4]
    allowed_config = {
        "language": allowed("language", {"ko", "en"}),
        "audience": allowed("audience", {"default", "nondev", "guided"}),
        "approval": allowed("approval", {"ask", "workspace"}),
        "panels": " ".join(panels),
        "relay": allowed("relay", {"off", "ready", "auto"}),
    }
    proof_verdict = str((state.get("proof") or {}).get("verdict", ""))
    if proof_verdict not in {"", "ready", "review", "empty"}:
        proof_verdict = "invalid"
    next_action = str(state.get("next", ""))
    if next_action not in {
        "", "knowledge", "schedule", "test", "test-status", "test-finish",
        "race-status", "goal", "proof",
    }:
        next_action = "invalid"
    return {
        "schema": 1,
        "generated_at": int(time.time()),
        "rondo": {"version": version, **installation},
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "repository": {
            "id": repo_key(root),
            "branch_kind": (
                "default" if branch in {"main", "master"}
                else "detached" if branch == "(detached)"
                else "other"
            ),
            "changed": int(state.get("changed", 0)),
        },
        "configuration": allowed_config,
        "agents": {
            name: bool(agents.get(name, False)) for name in sorted(agent_names)
        },
        "workflow": {
            "knowledge_pending": int(state.get("knowledge_pending", 0)),
            "jobs_pending": int(state.get("jobs_pending", 0)),
            "jobs_active": int(state.get("jobs_active", 0)),
            "test_complete": int((state.get("test") or {}).get("complete", 0)),
            "test_total": int((state.get("test") or {}).get("total", 0)),
            "race_agents": int((state.get("race") or {}).get("agents", 0)),
            "proof_verdict": proof_verdict,
            "next": next_action,
        },
    }


def create(destination: Path, value: dict) -> Path:
    destination = destination.with_suffix(".zip") if destination.suffix.lower() != ".zip" else destination
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_symlink() or destination.exists() or destination.parent.is_symlink():
        raise SupportError("destination_unsafe")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise SupportError("destination_unsafe")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.json", json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            archive.writestr(
                "README.txt",
                "Rondo support bundle\n"
                "This archive contains allowlisted metadata only. It excludes prompts, "
                "transcripts, task text, file names, Git remotes, environment variables, "
                "credentials, and source code. Review report.json before sharing.\n",
            )
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
