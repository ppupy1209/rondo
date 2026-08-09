#!/usr/bin/env python3
"""Real Zellij delivery and restart smoke test; run explicitly in CI."""
from __future__ import annotations

import fcntl
import json
import os
import pty
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RONDO = ROOT / "bin" / "rondo"
FAKE_AGENT = ROOT / "tests" / "fixtures" / "fake_agent.py"


def command(env: dict[str, str], name: str, *args: str, check: bool = True):
    return subprocess.run(
        ["zellij", "-s", name, *args], env=env,
        capture_output=True, text=True, timeout=15, check=check,
    )


def wait_for(env: dict[str, str], name: str, marker: str = "FAKE_AGENT_READY") -> list[dict]:
    deadline = time.monotonic() + 20
    last_error = "session did not appear"
    while time.monotonic() < deadline:
        try:
            panes = json.loads(command(env, name, "action", "list-panes", "--json").stdout)
            agent = next(item for item in panes if item.get("title") == "codex")
            screen = command(
                env, name, "action", "dump-screen", "--pane-id", str(agent["id"])
            ).stdout
            if marker in screen:
                return panes
            last_error = screen
        except subprocess.CalledProcessError as error:
            last_error = (error.stderr or error.stdout or str(error)).strip()
        except (OSError, subprocess.SubprocessError, ValueError, StopIteration) as error:
            last_error = str(error)
        time.sleep(0.2)
    raise RuntimeError(last_error)


def start(env: dict[str, str], name: str, repo: Path):
    layout = "\n".join([
        "layout {",
        '  tab name="agents" {',
        f'    pane name="codex" command={json.dumps(sys.executable)} cwd={json.dumps(str(repo))} {{',
        f'      args {json.dumps(str(FAKE_AGENT))}',
        "    }",
        "  }",
        '  tab name="shell" focus=true {',
        f'    pane name="shell" cwd={json.dumps(str(repo))}',
        "  }",
        "}",
    ])
    layout_path = repo.parent / "layout.kdl"
    layout_path.write_text(layout + "\n", encoding="utf-8")
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
    process = subprocess.Popen(
        ["zellij", "-s", name, "-n", str(layout_path)],
        stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True,
    )
    os.close(slave)
    return process, master


def stop(env: dict[str, str], name: str, process, master: int) -> None:
    subprocess.run(
        ["zellij", "delete-session", "--force", name], env=env,
        capture_output=True, text=True, timeout=15, check=False,
    )
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    os.close(master)


def cycle(env: dict[str, str], name: str, repo: Path, token: str) -> None:
    process, master = start(env, name, repo)
    try:
        try:
            panes = wait_for(env, name)
        except RuntimeError as error:
            os.set_blocking(master, False)
            chunks = []
            while True:
                try:
                    chunk = os.read(master, 65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                except OSError:
                    break
            detail = b"".join(chunks).decode("utf-8", "replace")[-4000:]
            raise RuntimeError(
                f"{error}\nprocess={process.poll()}\nZellij PTY:\n{detail}"
            ) from None
        shell = next(item for item in panes if item.get("title") == "shell")
        send_env = env | {
            "ZELLIJ_SESSION_NAME": name,
            "ZELLIJ_PANE_ID": str(shell["id"]),
            "RONDO_LANG": "en",
        }
        sent = subprocess.run(
            [sys.executable, str(RONDO), "send", "codex", token],
            cwd=repo, env=send_env, capture_output=True, text=True, timeout=20,
        )
        if sent.returncode:
            raise RuntimeError(sent.stderr or sent.stdout)
        wait_for(env, name, "RECEIVED:" + token)
    finally:
        stop(env, name, process, master)


def main() -> int:
    if os.name == "nt":
        print("Zellij PTY smoke is Unix-only")
        return 0
    if shutil.which("zellij") is None:
        raise RuntimeError("zellij is required")
    # Zellij encodes the socket path into an OS-local address with a strict
    # length limit. Keep this test path short on macOS as Rondo itself does.
    with tempfile.TemporaryDirectory(prefix="rz-", dir="/tmp") as directory:
        base = Path(directory)
        repo = base / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        socket = base / "socket"
        config = base / "zellij-config"
        socket.mkdir()
        config.mkdir()
        env = os.environ.copy()
        env.update({
            "ZELLIJ_SOCKET_DIR": str(socket),
            "ZELLIJ_CONFIG_DIR": str(config),
            "XDG_CONFIG_HOME": str(base / "config"),
            "XDG_CACHE_HOME": str(base / "cache"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        name = "rondo-e2e-" + uuid.uuid4().hex[:10]
        cycle(env, name, repo, "E2E_FIRST_VISIBLE")
        cycle(env, name, repo, "E2E_AFTER_FORCED_RESTART")
    print("real Zellij delivery and forced restart: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
