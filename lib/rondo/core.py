"""Rondo's small, standard-library-only coordination core.

Rondo deliberately does not proxy provider APIs or preserve full transcripts.  It
coordinates the native Claude, Codex and Gemini CLIs through a bounded project-
local state directory and visible messages.
"""

from __future__ import annotations

import contextlib
import ctypes
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from . import __version__


AGENTS = ("claude", "codex", "gemini")
DISPLAY_NAMES = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini"}
DEFAULT_CONFIG = {
    "schema": 1,
    "agents": list(AGENTS),
    "context": True,
    "failover": "auto",
    "failover_order": list(AGENTS),
    "verification": "independent",
}
MAX_CONTEXT_BYTES = 32 * 1024
MAX_MESSAGES_BYTES = 1024 * 1024
MAX_CHECKPOINTS = 40
MAX_HANDOFFS = 30
BLOCKING_PROMPTS = (
    "do you trust this folder",
    "do you trust this directory",
    "do you trust the authors",
    "is this a project you created or one you trust",
    "allow this command",
    "approve this",
    "would you like to proceed",
    "do you want to proceed",
    "select an option",
)
QUOTA_PATTERNS = (
    re.compile(r"\busage limit (?:has been )?reached\b", re.I),
    re.compile(r"\byou(?:'ve| have) hit your (?:usage )?limit\b", re.I),
    re.compile(r"\bquota (?:is )?(?:exhausted|exceeded)\b", re.I),
    re.compile(r"\b(?:usage|limit)[^\n]{0,80}\b0\s*%\s*(?:remaining|left)\b", re.I),
    re.compile(r"\byou have 0 weighted tokens left\b", re.I),
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\b(?:sk|ghp|github_pat|glpat)-?[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{12,}"),
)


class RondoError(RuntimeError):
    """A safe, user-facing Rondo error."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def display_name(agent: str) -> str:
    return DISPLAY_NAMES.get(agent, agent.title())


def normalize_agent(agent: str) -> str:
    value = (agent or "").strip().lower()
    if value not in AGENTS:
        raise RondoError("지원하는 AI는 claude, codex, gemini뿐입니다.")
    return value


def redact(value: object) -> str:
    text = str(value or "").replace("\x00", "")
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: "%s=[REDACTED]" % m.group(1), text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text[:12000]


def find_project_root(start: Optional[Path] = None) -> Path:
    base = Path(start or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return base


def state_dir(root: Path) -> Path:
    return Path(root).resolve() / ".rondo"


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def ensure_safe_state_dir(root: Path) -> Path:
    root = Path(root).resolve()
    target = root / ".rondo"
    if target.exists() and (target.is_symlink() or _is_reparse_point(target) or not target.is_dir()):
        raise RondoError(".rondo 경로가 링크이거나 디렉터리가 아니어서 사용하지 않았습니다.")
    if os.name == "nt":
        target.mkdir(parents=False, exist_ok=True)
    else:
        target.mkdir(mode=0o700, parents=False, exist_ok=True)
    if os.name != "nt":
        try:
            target.chmod(0o700)
        except OSError:
            pass
    return target


def _refuse_unsafe_file(path: Path) -> None:
    if path.exists() and (path.is_symlink() or _is_reparse_point(path) or not path.is_file()):
        raise RondoError("%s 경로가 링크이거나 일반 파일이 아니어서 사용하지 않았습니다." % path.name)
    if path.is_symlink():
        raise RondoError("%s 경로가 링크여서 사용하지 않았습니다." % path.name)


def _atomic_write(path: Path, content: str) -> None:
    _refuse_unsafe_file(path)
    if os.name == "nt":
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent), text=True)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        os.replace(str(temporary_path), str(path))
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()


def _write_json(path: Path, value: dict) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path, default: dict) -> dict:
    _refuse_unsafe_file(path)
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RondoError("%s 파일을 읽을 수 없습니다: %s" % (path.name, exc)) from exc
    if not isinstance(value, dict):
        raise RondoError("%s 파일 형식이 올바르지 않습니다." % path.name)
    return value


@contextlib.contextmanager
def project_lock(root: Path, timeout: float = 5.0) -> Iterator[None]:
    directory = ensure_safe_state_dir(root)
    lock_path = directory / "lock"
    _refuse_unsafe_file(lock_path)
    handle = open(lock_path, "a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    if os.name != "nt":
        with contextlib.suppress(OSError):
            os.chmod(lock_path, 0o600)
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise RondoError("다른 Rondo 작업이 상태를 갱신 중입니다. 잠시 후 다시 시도하세요.")
                time.sleep(0.05)
        yield
    finally:
        if locked:
            with contextlib.suppress(OSError):
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def default_state() -> dict:
    return {
        "schema": 1,
        "task": {"goal": "", "status": "idle", "owner": None, "implementers": []},
        "sessions": {},
        "relay": {"status": "closed", "pane_id": ""},
        "checkpoints": [],
        "handoffs": [],
        "review": {"status": "not_requested"},
    }


def validate_config(value: dict) -> dict:
    result = dict(DEFAULT_CONFIG)
    result.update(value)
    agents = result.get("agents")
    if not isinstance(agents, list) or not agents:
        raise RondoError("최소 한 개의 AI를 활성화해야 합니다.")
    clean: List[str] = []
    for agent in agents:
        normalized = normalize_agent(str(agent))
        if normalized not in clean:
            clean.append(normalized)
    result["agents"] = clean
    if result.get("context") not in (True, False):
        raise RondoError("context 값은 true 또는 false여야 합니다.")
    if result.get("failover") not in ("auto", "ask", "off"):
        raise RondoError("failover 값은 auto, ask, off 중 하나여야 합니다.")
    order: List[str] = []
    for item in result.get("failover_order", clean):
        normalized = normalize_agent(str(item))
        if normalized in clean and normalized not in order:
            order.append(normalized)
    result["failover_order"] = order + [item for item in clean if item not in order]
    result["verification"] = "independent"
    result["schema"] = 1
    return result


def load_config(root: Path) -> dict:
    directory = ensure_safe_state_dir(root)
    return validate_config(_read_json(directory / "config.json", DEFAULT_CONFIG))


def save_config(root: Path, value: dict) -> dict:
    result = validate_config(value)
    ensure_safe_state_dir(root)
    _write_json(state_dir(root) / "config.json", result)
    return result


def load_state(root: Path) -> dict:
    directory = ensure_safe_state_dir(root)
    value = _read_json(directory / "state.json", default_state())
    baseline = default_state()
    for key, default in baseline.items():
        value.setdefault(key, default)
    return value


def save_state(root: Path, value: dict) -> None:
    value["schema"] = 1
    _write_json(state_dir(root) / "state.json", value)


def add_git_exclude(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0 or not result.stdout.strip():
        return False
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = Path(root) / exclude
    exclude = Path(os.path.abspath(str(exclude)))
    exclude.parent.mkdir(parents=True, exist_ok=True)
    _refuse_unsafe_file(exclude)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    lines = [line.strip() for line in existing.splitlines()]
    if "/.rondo/" not in lines:
        with exclude.open("a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith(("\n", "\r")):
                handle.write("\n")
            handle.write("/.rondo/\n")
    return True


def init_project(root: Path, config: Optional[dict] = None) -> Tuple[dict, dict]:
    ensure_safe_state_dir(root)
    with project_lock(root):
        add_git_exclude(root)
        selected = save_config(root, config or load_config(root))
        state = load_state(root)
        save_state(root, state)
        render_context(root, state, selected)
    return selected, state


def _git_summary(root: Path) -> Tuple[str, str, str]:
    def run(args: Sequence[str]) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=8, check=False
            )
            return redact(result.stdout.strip()) if result.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    return run(["branch", "--show-current"]), run(["status", "--short"]), run(["diff", "--stat"])


def render_context(root: Path, state: Optional[dict] = None, config: Optional[dict] = None) -> None:
    state = state or load_state(root)
    config = config or load_config(root)
    target = state_dir(root) / "context.md"
    _refuse_unsafe_file(target)
    if not config["context"]:
        with contextlib.suppress(FileNotFoundError):
            target.unlink()
        return
    task = state.get("task", {})
    branch, status, diff_stat = _git_summary(root)
    lines = [
        "# Rondo context",
        "",
        "> Structured project state only. No full transcript or hidden reasoning is stored.",
        "",
        "## Task",
        "",
        "- Goal: %s" % (redact(task.get("goal")) or "Not set"),
        "- Status: %s" % redact(task.get("status", "idle")),
        "- Current owner: %s" % (redact(task.get("owner")) or "None"),
        "- Implementer sessions: %s" % (", ".join(task.get("implementers", [])) or "None"),
        "",
        "## Recent checkpoints",
        "",
    ]
    checkpoints = state.get("checkpoints", [])[-12:]
    lines.extend(
        "- [%s] %s/%s: %s" % (item.get("time", ""), item.get("agent", "?"), item.get("session", "?")[:8], redact(item.get("summary")))
        for item in checkpoints
    )
    if not checkpoints:
        lines.append("- None")
    lines.extend(["", "## Recent handoffs", ""])
    handoffs = state.get("handoffs", [])[-8:]
    lines.extend(
        "- [%s] %s -> %s (%s): %s" % (
            item.get("time", ""), item.get("from", "?"), item.get("to", "?"), item.get("reason", "manual"), redact(item.get("summary"))
        )
        for item in handoffs
    )
    if not handoffs:
        lines.append("- None")
    review = state.get("review", {})
    lines.extend(
        [
            "",
            "## Independent review",
            "",
            "- Status: %s" % redact(review.get("status", "not_requested")),
            "- Reviewer: %s" % (redact(review.get("reviewer")) or "None"),
            "- Summary: %s" % (redact(review.get("summary")) or "None"),
            "",
            "## Git working tree",
            "",
            "- Branch: %s" % (branch or "Not a Git repository"),
            "- Status:",
            "```text",
            status or "clean",
            "```",
            "- Diff summary:",
            "```text",
            diff_stat or "none",
            "```",
            "",
            "## Next action",
            "",
            redact(handoffs[-1].get("summary")) if handoffs else "Continue the task, then create a checkpoint.",
            "",
        ]
    )
    content = "\n".join(lines)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_CONTEXT_BYTES:
        content = encoded[: MAX_CONTEXT_BYTES - 80].decode("utf-8", "ignore") + "\n\n[Context truncated by Rondo.]\n"
    _atomic_write(target, content)


def _rotate_messages(path: Path) -> None:
    _refuse_unsafe_file(path)
    if not path.exists() or path.stat().st_size < MAX_MESSAGES_BYTES:
        return
    rotated = path.with_name("messages.1.jsonl")
    _refuse_unsafe_file(rotated)
    with contextlib.suppress(FileNotFoundError):
        rotated.unlink()
    os.replace(str(path), str(rotated))


def append_message(root: Path, sender: str, recipient: str, text: str, kind: str = "message", session: str = "") -> dict:
    directory = ensure_safe_state_dir(root)
    message = {
        "time": utc_now(),
        "from": sender,
        "to": recipient,
        "kind": kind,
        "session": session,
        "text": redact(text),
    }
    with project_lock(root):
        path = directory / "messages.jsonl"
        _rotate_messages(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        descriptor = os.open(str(path), flags, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(message, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return message


def recent_messages(root: Path, count: int = 50) -> List[dict]:
    path = state_dir(root) / "messages.jsonl"
    _refuse_unsafe_file(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, count):]
    result = []
    for line in lines:
        with contextlib.suppress(json.JSONDecodeError):
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
    return result


def session_identity() -> Tuple[str, str]:
    agent = os.environ.get("RONDO_AGENT", "").lower()
    session = os.environ.get("RONDO_SESSION_ID", "")
    return agent, session


def register_session(root: Path, agent: str, session: str, pane_id: str = "", role: str = "worker") -> None:
    agent = normalize_agent(agent)
    with project_lock(root):
        state = load_state(root)
        state["sessions"][session] = {
            "agent": agent,
            "pane_id": str(pane_id or ""),
            "role": role,
            "status": "active",
            "started_at": utc_now(),
            "last_seen": utc_now(),
        }
        if len(state["sessions"]) > 48:
            closed = sorted(
                (
                    (sid, data) for sid, data in state["sessions"].items()
                    if data.get("status") != "active" and sid != session
                ),
                key=lambda item: item[1].get("last_seen", ""),
            )
            for old_session, _data in closed[: len(state["sessions"]) - 48]:
                state["sessions"].pop(old_session, None)
        save_state(root, state)
        render_context(root, state)
    append_message(root, "Rondo", display_name(agent), "%s session connected (%s)." % (display_name(agent), session[:8]), "session")


def close_session(root: Path, session: str, status: str = "closed") -> None:
    with project_lock(root):
        state = load_state(root)
        if session in state["sessions"]:
            state["sessions"][session]["status"] = status
            state["sessions"][session]["last_seen"] = utc_now()
            save_state(root, state)
            render_context(root, state)


def register_relay(root: Path, pane_id: str) -> None:
    with project_lock(root):
        state = load_state(root)
        state["relay"] = {"status": "active", "pane_id": str(pane_id or ""), "last_seen": utc_now()}
        save_state(root, state)


def close_relay(root: Path) -> None:
    with project_lock(root):
        state = load_state(root)
        state["relay"] = {"status": "closed", "pane_id": "", "last_seen": utc_now()}
        save_state(root, state)


def set_task(root: Path, goal: str, agent: str = "", session: str = "") -> None:
    with project_lock(root):
        state = load_state(root)
        clean_goal = redact(goal)
        if state["task"].get("goal") != clean_goal:
            state["task"] = {"goal": clean_goal, "status": "in_progress", "owner": None, "implementers": []}
            state["checkpoints"] = []
            state["handoffs"] = []
        else:
            state["task"].update({"goal": clean_goal, "status": "in_progress"})
        if agent:
            state["task"]["owner"] = agent
        if session and session not in state["task"]["implementers"]:
            state["task"]["implementers"].append(session)
        state["review"] = {"status": "not_requested"}
        save_state(root, state)
        render_context(root, state)


def checkpoint(root: Path, summary: str, agent: str, session: str) -> dict:
    if not agent or not session:
        raise RondoError("checkpoint는 Rondo가 연 AI 세션 안에서 실행해야 합니다.")
    agent = normalize_agent(agent)
    item = {"time": utc_now(), "agent": agent, "session": session, "summary": redact(summary)}
    with project_lock(root):
        state = load_state(root)
        task = state["task"]
        task["status"] = "in_progress"
        task["owner"] = agent
        if session not in task["implementers"]:
            task["implementers"].append(session)
        state["checkpoints"].append(item)
        state["checkpoints"] = state["checkpoints"][-MAX_CHECKPOINTS:]
        state["review"] = {"status": "not_requested"}
        save_state(root, state)
        render_context(root, state)
    append_message(root, display_name(agent), "All", item["summary"], "checkpoint", session)
    return item


def quota_exhausted(screen: str) -> bool:
    value = (screen or "")[-12000:]
    return any(pattern.search(value) for pattern in QUOTA_PATTERNS)


def screen_is_blocked(screen: str) -> bool:
    lowered = (screen or "")[-6000:].lower()
    return any(pattern in lowered for pattern in BLOCKING_PROMPTS)


def choose_target(
    state: dict,
    config: dict,
    source_agent: str = "",
    requested: str = "",
    independent: bool = False,
    source_session: str = "",
) -> Tuple[str, Optional[str]]:
    requested = normalize_agent(requested) if requested else ""
    implementers = set(state.get("task", {}).get("implementers", []))
    active = [
        (sid, data)
        for sid, data in state.get("sessions", {}).items()
        if data.get("status") == "active"
        and data.get("agent") in config["agents"]
        and (independent or data.get("role", "worker") == "worker")
    ]
    order = [requested] if requested else list(config.get("failover_order", config["agents"]))
    order += [agent for agent in config["agents"] if agent not in order]
    for agent in order:
        if not requested and agent == source_agent and len(config["agents"]) > 1:
            continue
        for sid, data in reversed(active):
            if source_session and sid == source_session:
                continue
            if data.get("agent") != agent:
                continue
            if independent and sid in implementers:
                continue
            return agent, sid
    if independent:
        for agent in order:
            if agent in config["agents"]:
                return agent, None
    raise RondoError("인계할 활성 AI 세션이 없습니다. Rondo 화면에서 대상 AI 탭을 먼저 여세요.")


def zellij_session_name() -> str:
    return os.environ.get("ZELLIJ_SESSION_NAME", "")


def zellij_executable() -> str:
    """Return the bundled Zellij path when a launcher supplied one."""
    if os.name != "nt":
        socket_dir = Path("/tmp") / ("rondo-zellij-%s" % os.getuid())
        try:
            socket_dir.mkdir(mode=0o700, exist_ok=True)
            info = socket_dir.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise OSError("unsafe owner or file type")
            socket_dir.chmod(0o700)
        except OSError as error:
            raise RondoError("Zellij 소켓 디렉터리를 안전하게 준비할 수 없습니다: %s" % error) from error
        os.environ["ZELLIJ_SOCKET_DIR"] = str(socket_dir)
    override = os.environ.get("RONDO_ZELLIJ_PATH", "").strip()
    return override or (shutil.which("zellij") or "")


def dump_pane(session_name: str, pane_id: str, timeout: float = 5.0) -> str:
    if not session_name or not pane_id:
        return ""
    try:
        result = subprocess.run(
            [zellij_executable(), "-s", session_name, "action", "dump-screen", "--pane-id", str(pane_id)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def deliver_to_session(root: Path, target_session: str, prompt: str) -> bool:
    state = load_state(root)
    target = state.get("sessions", {}).get(target_session, {})
    pane_id = str(target.get("pane_id", ""))
    session_name = zellij_session_name() or os.environ.get("RONDO_ZELLIJ_SESSION", "")
    if not pane_id or not session_name:
        return False
    if screen_is_blocked(dump_pane(session_name, pane_id)):
        raise RondoError("대상 AI가 승인 또는 선택을 기다리고 있어 메시지만 Relay에 남겼습니다.")
    commands = (
        [zellij_executable(), "-s", session_name, "action", "paste", "--pane-id", pane_id, "--", prompt],
        [zellij_executable(), "-s", session_name, "action", "send-keys", "--pane-id", pane_id, "Enter"],
    )
    for command in commands:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode != 0:
            return False
    return True


def handoff(root: Path, source_agent: str, source_session: str, summary: str, requested: str = "", reason: str = "manual") -> dict:
    source_agent = normalize_agent(source_agent) if source_agent else "user"
    config = load_config(root)
    with project_lock(root):
        state = load_state(root)
        target_agent, target_session = choose_target(
            state, config, source_agent, requested, source_session=source_session
        )
        item = {
            "time": utc_now(), "from": source_agent, "from_session": source_session,
            "to": target_agent, "to_session": target_session, "reason": reason, "summary": redact(summary),
        }
        state["handoffs"].append(item)
        state["handoffs"] = state["handoffs"][-MAX_HANDOFFS:]
        state["task"]["owner"] = target_agent
        state["task"]["status"] = "in_progress"
        if source_session and source_session not in state["task"]["implementers"]:
            state["task"]["implementers"].append(source_session)
        if reason == "quota" and source_session in state["sessions"]:
            state["sessions"][source_session]["status"] = "quota_exhausted"
        save_state(root, state)
        render_context(root, state, config)
    if config["context"]:
        text = "%s. .rondo/context.md를 읽고 이어서 작업하세요." % item["summary"]
    else:
        text = "%s. 공유 맥락이 꺼져 있으므로 이 공개 요약만 바탕으로 이어서 작업하세요." % item["summary"]
    append_message(root, display_name(source_agent), display_name(target_agent), text, "handoff", source_session)
    try:
        item["delivered"] = bool(target_session and deliver_to_session(root, target_session, text))
    except RondoError as error:
        item["delivered"] = False
        item["delivery_error"] = str(error)
    return item


def request_review(root: Path, agent: str, session: str, requested: str = "") -> dict:
    if not agent or not session:
        raise RondoError("검증 요청은 Rondo가 연 AI 세션 안에서 실행해야 합니다.")
    config = load_config(root)
    with project_lock(root):
        state = load_state(root)
        if session not in state["task"]["implementers"]:
            state["task"]["implementers"].append(session)
        reviewer_agent, reviewer_session = choose_target(state, config, agent, requested, independent=True)
        review = {
            "status": "requested", "requested_at": utc_now(), "requested_by": session,
            "agent": reviewer_agent, "reviewer": reviewer_session, "summary": "",
        }
        state["review"] = review
        state["task"]["status"] = "review"
        save_state(root, state)
        render_context(root, state, config)
    text = "독립 검증 요청: 구현 세션과 분리해서 변경사항을 테스트·검토하고 `rondo review pass|fail \"요약\"`으로 결과를 남기세요."
    append_message(root, display_name(agent), display_name(reviewer_agent), text, "review_request", session)
    try:
        review["delivered"] = bool(reviewer_session and deliver_to_session(root, reviewer_session, text))
    except RondoError as error:
        review["delivered"] = False
        review["delivery_error"] = str(error)
    return review


def record_review(root: Path, verdict: str, summary: str, agent: str, session: str) -> dict:
    if verdict not in ("pass", "fail"):
        raise RondoError("검증 결과는 pass 또는 fail이어야 합니다.")
    if not agent or not session:
        raise RondoError("검증 결과는 Rondo가 연 독립 AI 세션에서 기록해야 합니다.")
    with project_lock(root):
        state = load_state(root)
        if session in set(state["task"].get("implementers", [])):
            raise RondoError("구현에 참여한 세션은 최종 검증자가 될 수 없습니다. 다른 AI 또는 새 세션을 사용하세요.")
        requested = state.get("review", {})
        assigned = requested.get("reviewer")
        if assigned and assigned != session:
            raise RondoError("이 검증은 다른 독립 세션에 배정되어 있습니다.")
        review = {
            "status": "passed" if verdict == "pass" else "failed", "reviewed_at": utc_now(),
            "agent": normalize_agent(agent), "reviewer": session, "summary": redact(summary),
        }
        state["review"] = review
        state["task"]["status"] = "done" if verdict == "pass" else "in_progress"
        save_state(root, state)
        render_context(root, state)
    append_message(root, display_name(agent), "All", review["summary"], "review_%s" % verdict, session)
    return review


def provider_executable(agent: str) -> Optional[str]:
    agent = normalize_agent(agent)
    override = os.environ.get("RONDO_%s_COMMAND" % agent.upper())
    if override:
        return override
    if agent == "gemini":
        return shutil.which("gemini") or shutil.which("agy")
    return shutil.which(agent)


def protocol_prompt(root: Path, agent: str, role: str = "worker") -> str:
    context = state_dir(root) / "context.md"
    if role == "reviewer":
        duty = "You are an independent reviewer. Do not implement unless a failed review is handed back. Test and review, then run rondo review pass|fail SUMMARY."
    else:
        duty = "You may run development checks, but you must not certify your own implementation. At milestones run rondo checkpoint SUMMARY; when ready run rondo request-review."
    return (
        "Rondo is only a lightweight coordinator; the native %s CLI remains the main tool. "
        "Read %s when it exists. %s Send all cross-agent communication with "
        "rondo message AGENT TEXT so it stays visible in Relay. Never put secrets or hidden reasoning in Rondo state."
    ) % (display_name(agent), context, duty)


def provider_command(agent: str, root: Path, role: str = "worker") -> List[str]:
    executable = provider_executable(agent)
    if not executable:
        raise RondoError("%s CLI가 PATH에 없습니다. 먼저 공식 CLI를 설치하세요." % display_name(agent))
    prompt = protocol_prompt(root, agent, role)
    if agent == "claude":
        return [executable, "--append-system-prompt", prompt]
    if agent == "codex":
        return [executable, "-c", "developer_instructions='%s'" % prompt.replace("'", "’")]
    return [executable, "--prompt-interactive", prompt]


def session_name(root: Path) -> str:
    root = Path(root).resolve()
    origin = ""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        result = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        origin = result.stdout.strip()
    key = origin or str(root).lower()
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", root.name).strip("-").lower() or "project"
    return "rondo-%s-%s" % (slug[:30], hashlib.sha256(key.encode("utf-8")).hexdigest()[:10])


def _pid_is_live_zellij(pid: int) -> Optional[bool]:
    if os.name != "nt" or pid <= 0:
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return False
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return Path(buffer.value).name.lower() in ("zellij.exe", "zellij")
    finally:
        kernel32.CloseHandle(handle)


def cleanup_stale_windows_marker(name: str) -> bool:
    if os.name != "nt" or not re.fullmatch(r"rondo-[a-z0-9-]+", name):
        return False
    base = Path(tempfile.gettempdir()).resolve() / "zellij" / "contract_version_1"
    marker = base / name
    if not marker.exists() or marker.is_symlink() or _is_reparse_point(marker) or not marker.is_file():
        return False
    try:
        pid = int(marker.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeError, ValueError):
        return False
    if _pid_is_live_zellij(pid) is not False:
        return False
    marker.unlink()
    return True


def zellij_session_exists(name: str) -> bool:
    try:
        executable = zellij_executable()
        if not executable:
            return False
        result = subprocess.run(
            [executable, "list-sessions", "--short"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=8, check=False,
        )
        return result.returncode == 0 and name in {line.strip() for line in result.stdout.splitlines()}
    except (OSError, subprocess.SubprocessError):
        return False


def format_message(item: dict) -> str:
    stamp = str(item.get("time", ""))[11:19] or "--:--:--"
    return "[%s] %s -> %s [%s] %s" % (
        stamp, item.get("from", "?"), item.get("to", "?"), item.get("kind", "message"), item.get("text", "")
    )


def version() -> str:
    return __version__
