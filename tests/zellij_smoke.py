#!/usr/bin/env python3
"""Open split Rondo panes and verify visible delivery through Zellij on Unix."""

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
FAKE = ROOT / "tests" / "fixtures" / "fake_agent.py"


def zellij(env, name, *args, check=True):
    return subprocess.run(
        ["zellij", "-s", name, *args], env=env, capture_output=True,
        text=True, timeout=15, check=check,
    )


def panes(env, name):
    return json.loads(zellij(env, name, "action", "list-panes", "--json").stdout)


def wait_screen(env, name, title, marker):
    deadline = time.monotonic() + 30
    last = "session did not appear"
    while time.monotonic() < deadline:
        try:
            items = panes(env, name)
            pane = next(item for item in items if item.get("title") == title or item.get("tab_name") == title)
            last = zellij(env, name, "action", "dump-screen", "--pane-id", str(pane["id"])).stdout
            if marker in last:
                return items
        except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as error:
            last = str(error)
        time.sleep(0.25)
    raise RuntimeError("%s: %s" % (marker, last[-2000:]))


def main():
    if os.name == "nt":
        return 0
    if not shutil.which("zellij"):
        raise RuntimeError("zellij is required")
    with tempfile.TemporaryDirectory(prefix="rz-", dir="/tmp") as temporary:
        base = Path(temporary)
        repo = base / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        fake = base / "fake-agent"
        fake.write_text("#!/bin/sh\nexec python3 %s \"$@\"\n" % json.dumps(str(FAKE)), encoding="utf-8")
        fake.chmod(0o755)
        socket = base / "socket"
        config = base / "zellij-config"
        socket.mkdir()
        config.mkdir()
        env = os.environ.copy()
        env.update(
            {
                "PATH": str(ROOT / "bin") + os.pathsep + env["PATH"],
                "ZELLIJ_SOCKET_DIR": str(socket),
                "ZELLIJ_CONFIG_DIR": str(config),
                "RONDO_CLAUDE_COMMAND": str(fake),
                "RONDO_CODEX_COMMAND": str(fake),
                "RONDO_GEMINI_COMMAND": str(fake),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        configured = subprocess.run(
            [sys.executable, str(RONDO), "setup", "--agents", "claude,codex,gemini"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=15,
        )
        if configured.returncode:
            raise RuntimeError(configured.stderr or configured.stdout)
        sys.path.insert(0, str(ROOT / "lib"))
        from rondo import core

        name = core.session_name(repo)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 120, 0, 0))
        process = subprocess.Popen(
            [sys.executable, str(RONDO)], cwd=repo, env=env, stdin=slave,
            stdout=slave, stderr=slave, start_new_session=True,
        )
        os.close(slave)
        try:
            for title in ("Claude", "Codex", "Gemini"):
                wait_screen(env, name, title, "FAKE_AGENT_READY")
            agent_tabs = {
                item.get("title"): item.get("tab_name")
                for item in panes(env, name)
                if item.get("title") in ("Claude", "Codex", "Gemini")
            }
            if agent_tabs != {"Claude": "Agents", "Codex": "Agents", "Gemini": "Agents"}:
                raise RuntimeError("agents were not split in one tab: %r" % agent_tabs)
            token = "VISIBLE_" + uuid.uuid4().hex[:8]
            sent = subprocess.run(
                [sys.executable, str(RONDO), "message", "codex", token],
                cwd=repo, env=env, capture_output=True, text=True, timeout=15,
            )
            if sent.returncode:
                raise RuntimeError(sent.stderr or sent.stdout)
            wait_screen(env, name, "Codex", "RECEIVED:" + token)
            wait_screen(env, name, "Relay", token)
            if not (repo / ".rondo" / "context.md").is_file():
                raise RuntimeError("project context was not created")
        finally:
            subprocess.run(["zellij", "delete-session", "--force", name], env=env, capture_output=True, timeout=15)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
            os.close(master)
    print("real split Rondo panes and visible delivery: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
