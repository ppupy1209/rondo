"""Map one Rondo approval mode to each supported agent CLI."""
from __future__ import annotations

import os
from pathlib import Path

MODES = ("ask", "workspace")

WORKSPACE_ARGUMENTS = {
    "claude": ["--permission-mode", "acceptEdits"],
    "codex": ["--sandbox", "workspace-write", "--ask-for-approval", "never"],
    "gemini": ["--mode", "accept-edits"],
    "kimi": ["--auto"],
    "grok": ["--permission-mode", "auto"],
}


def selected(config: Path | None = None) -> str:
    forced = os.environ.get("RONDO_APPROVAL", "").lower()
    if forced in MODES:
        return forced
    if config is None:
        config = Path(os.environ.get(
            "XDG_CONFIG_HOME", Path.home() / ".config"
        )) / "rondo"
    try:
        saved = (config / "approval").read_text(encoding="utf-8").strip().lower()
    except OSError:
        saved = ""
    return saved if saved in MODES else "ask"


def arguments(agent: str, mode: str) -> list[str]:
    return list(WORKSPACE_ARGUMENTS.get(agent, ())) if mode == "workspace" else []
