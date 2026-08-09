"""git 호출 한 곳. race·undo 가 같이 쓴다."""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """사용자에게 그대로 보여줄 수 있는 실패."""


def git(root: Path | str, *args: str, check: bool = True, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args],
        input=stdin, capture_output=True, text=True, timeout=120,
    )
    if check and done.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout
