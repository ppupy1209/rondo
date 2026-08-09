"""Rondo Proof — 코드 전체 대신 재현 가능한 증거와 사람 판단 항목을 만든다."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .gitcmd import git
from .paths import CACHE, atomic_json, read_json, repo_key

CHECK_TIMEOUT = 300
OUTPUT_LIMIT = 8_000
LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}
HIGH_MARKERS = {
    "access", "acl", "auth", "billing", "checkout", "credential", "crypto",
    "database", "db", "delete", "deploy", "flyway", "invoice", "login",
    "migration", "oauth", "payment", "permission", "policy", "role", "schema",
    "secret", "security", "session", "sql", "terraform", "token", "webhook",
}
LOW_PARTS = {"test", "tests", "docs", "fixtures", "snapshots"}
LOW_SUFFIXES = {".md", ".txt", ".rst"}


def proof_home(root: Path) -> Path:
    return CACHE / "proof" / repo_key(root)


def task_path(root: Path) -> Path:
    return proof_home(root) / "task.json"


def latest_path(root: Path) -> Path:
    return proof_home(root) / "latest.json"


def record_task(
    root: Path,
    goal: str,
    acceptance: list[str] | None = None,
    must_not: list[str] | None = None,
    scope: list[str] | None = None,
    checks: list[list[str]] | None = None,
) -> dict:
    task = {
        "schema": 1,
        "goal": goal.strip(),
        "acceptance": [x.strip() for x in acceptance or [] if x.strip()],
        "must_not": [x.strip() for x in must_not or [] if x.strip()],
        "scope": [
            cleaned for x in scope or []
            if (cleaned := x.strip().strip("/\\"))
        ],
        "checks": [command for command in checks or [] if command],
        "created_at": int(time.time()),
    }
    if not task["goal"]:
        raise ValueError("task goal is empty")
    atomic_json(task_path(root), task)
    return task


def load_task(root: Path) -> dict:
    return read_json(task_path(root))


def changed_files(root: Path) -> list[str]:
    tracked = git(root, "diff", "--name-only", "HEAD", check=False).splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard", check=False).splitlines()
    return sorted({path for path in tracked + untracked if path})


def risk_for(path: str, scope: list[str] | None = None) -> dict:
    normalized = path.replace("\\", "/").strip("/")
    lowered = normalized.casefold()
    parts = set(Path(lowered).parts)
    tokens = set(re.split(r"[^a-z0-9]+", lowered))
    prefixes = [prefix.replace("\\", "/").strip("/").casefold() for prefix in scope or []]
    scoped = not prefixes or any(
        lowered == prefix or lowered.startswith(prefix + "/") for prefix in prefixes
    )
    if not scoped:
        return {"path": path, "level": "high", "reason": "scope_drift", "seconds": 90}
    if parts & HIGH_MARKERS or tokens & HIGH_MARKERS:
        return {"path": path, "level": "high", "reason": "sensitive_path", "seconds": 90}
    if parts & LOW_PARTS or Path(lowered).suffix in LOW_SUFFIXES:
        return {"path": path, "level": "low", "reason": "tests_or_docs", "seconds": 10}
    return {"path": path, "level": "medium", "reason": "code_change", "seconds": 35}


def discover_checks(root: Path) -> list[list[str]]:
    checks: list[list[str]] = []
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError, TypeError):
            scripts = {}
        for name in ("test", "lint"):
            if name in scripts:
                checks.append(["npm", "run", name])
    if (root / "tests").is_dir() and any((root / "tests").glob("test_*.py")):
        checks.append([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])
    if (root / "gradlew").is_file() or (root / "gradlew.bat").is_file():
        checks.append(["gradlew.bat" if os.name == "nt" else "./gradlew", "test"])
    if (root / "Cargo.toml").is_file():
        checks.append(["cargo", "test", "--quiet"])
    if (root / "go.mod").is_file():
        checks.append(["go", "test", "./..."])
    return checks[:3]


def run_check(root: Path, command: list[str]) -> dict:
    label = " ".join(command)
    executable = command[0]
    if not (shutil.which(executable) or (root / executable).exists()):
        return {"command": command, "label": label, "status": "missing", "seconds": 0, "output": ""}
    started = time.monotonic()
    try:
        done = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CHECK_TIMEOUT,
            env=os.environ | {"CI": "1", "PYTHONUTF8": "1"},
        )
        status = "passed" if done.returncode == 0 else "failed"
        output = (done.stdout + done.stderr)[-OUTPUT_LIMIT:]
        code = done.returncode
    except subprocess.TimeoutExpired as exc:
        status, code = "timeout", None
        output = f"Timed out after {CHECK_TIMEOUT}s\n{(exc.stdout or '')}{(exc.stderr or '')}"[-OUTPUT_LIMIT:]
    except OSError as exc:
        status, code, output = "missing", None, str(exc)
    return {
        "command": command,
        "label": label,
        "status": status,
        "returncode": code,
        "seconds": round(time.monotonic() - started, 2),
        "output": output,
    }


def _dedupe(commands: list[list[str]]) -> list[list[str]]:
    found = []
    seen = set()
    for command in commands:
        key = tuple(command)
        if key not in seen:
            found.append(command)
            seen.add(key)
    return found


def build(root: Path, run_checks: bool = True) -> dict:
    task = load_task(root)
    files = [risk_for(path, task.get("scope")) for path in changed_files(root)]
    commands = _dedupe([*(task.get("checks") or []), *discover_checks(root)])
    checks = [run_check(root, command) for command in commands] if run_checks else []

    human = []
    if not task:
        human.append({"level": "high", "label": "Task intent is not recorded", "seconds": 60})
    elif not task.get("acceptance"):
        human.append({"level": "medium", "label": "Acceptance criteria need confirmation", "seconds": 45})
    if not commands:
        human.append({"level": "medium", "label": "No executable checks were discovered", "seconds": 30})
    elif not run_checks:
        human.append({"level": "medium", "label": "Executable checks were skipped", "seconds": 30})
    for check in checks:
        if check["status"] != "passed":
            human.append({
                "level": "high",
                "label": f"Check {check['status']}: {check['label']}",
                "seconds": 90,
            })
    for item in files:
        if item["level"] == "high":
            human.append({
                "level": "high", "label": item["path"],
                "reason": item["reason"], "seconds": item["seconds"],
            })
    medium = [item["path"] for item in files if item["level"] == "medium"]
    if medium:
        human.append({
            "level": "medium",
            "label": f"Review {len(medium)} code file(s): {', '.join(medium[:4])}",
            "seconds": min(120, 30 + len(medium) * 10),
        })

    passed = sum(check["status"] == "passed" for check in checks)
    failed = sum(check["status"] != "passed" for check in checks)
    proof = {
        "schema": 1,
        "generated_at": int(time.time()),
        "root": str(root.resolve()),
        "branch": git(root, "branch", "--show-current", check=False).strip() or "(detached)",
        "head": git(root, "rev-parse", "--short", "HEAD", check=False).strip() or "-",
        "task": task,
        "files": files,
        "checks": checks,
        "human": human,
        "summary": {
            "files": len(files),
            "high": sum(item["level"] == "high" for item in files),
            "medium": sum(item["level"] == "medium" for item in files),
            "low": sum(item["level"] == "low" for item in files),
            "passed": passed,
            "failed": failed,
            "verdict": "ready" if task and task.get("acceptance") and commands and not human else "review",
        },
    }
    directory = proof_home(root)
    packet = directory / "latest.md"
    proof["packet"] = str(packet)
    atomic_json(latest_path(root), proof)
    _write_private(packet, markdown(proof))
    return proof


def latest(root: Path) -> dict:
    return read_json(latest_path(root))


def parse_budget(value: str) -> int:
    value = value.strip().lower()
    multiplier = 60 if value.endswith("m") else 1
    number = value[:-1] if value.endswith(("m", "s")) else value
    seconds = int(float(number) * multiplier)
    if seconds <= 0:
        raise ValueError("budget must be positive")
    return seconds


def review_queue(proof: dict, budget: int = 120) -> tuple[list[dict], list[dict]]:
    items = sorted(proof.get("human") or [], key=lambda item: LEVEL_ORDER[item["level"]])
    selected, deferred, spent = [], [], 0
    for item in items:
        if not selected or spent + item["seconds"] <= budget:
            selected.append(item)
            spent += item["seconds"]
        else:
            deferred.append(item)
    return selected, deferred


def markdown(proof: dict) -> str:
    task = proof.get("task") or {}
    summary = proof["summary"]
    lines = [
        "# Rondo Proof", "",
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}", "",
        "## Decision", "",
        f"- Verdict: **{summary['verdict']}**",
        f"- Checks: {summary['passed']} passed, {summary['failed']} unresolved",
        f"- Changed files: {summary['files']} (high {summary['high']}, medium {summary['medium']}, low {summary['low']})",
        "", "## Intent", "",
        task.get("goal") or "Task intent was not recorded.", "",
        "### Acceptance criteria", "",
    ]
    lines += [f"- {item}" for item in task.get("acceptance") or []] or ["- Not specified"]
    lines += ["", "### Must not change", ""]
    lines += [f"- {item}" for item in task.get("must_not") or []] or ["- Not specified"]
    lines += ["", "## Risk map", "", "| Risk | File | Reason |", "|---|---|---|"]
    for item in proof.get("files") or []:
        path = item["path"].replace("|", "\\|")
        lines.append(f"| {item['level']} | `{path}` | {item['reason']} |")
    if not proof.get("files"):
        lines.append("| low | No changed files | - |")
    lines += ["", "## Executable evidence", ""]
    for check in proof.get("checks") or []:
        lines += [
            f"### {check['status']}: `{check['label']}`", "",
            f"Duration: {check['seconds']}s", "", "```text",
            check.get("output") or "(no output)", "```", "",
        ]
    if not proof.get("checks"):
        lines += ["No checks were run.", ""]
    lines += ["## Human review queue", ""]
    for item in proof.get("human") or []:
        lines.append(f"- **{item['level']}** · {item['label']} · ~{item['seconds']}s")
    if not proof.get("human"):
        lines.append("- No mandatory human review item was found.")
    return "\n".join(lines) + "\n"


def _write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(value, encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
