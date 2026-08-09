"""rondo undo — 에이전트가 망친 작업 트리를 한 걸음 되돌린다.

각 CLI 에도 자체 rewind 가 있지만 **자기 턴만** 안다. 세 에이전트가 같은 트리를 만졌을 때
되돌릴 수 있는 건 워크스페이스를 소유한 Rondo 뿐이다.

## 스냅샷을 만드는 법

`git stash create` 는 untracked 를 안 담는다. 에이전트는 새 파일을 계속 만들므로 쓸 수 없다.
대신 **임시 인덱스**로 커밋 객체만 만든다 — 진짜 인덱스도, 작업 트리도, 브랜치도 안 건드린다.

    GIT_INDEX_FILE=<임시> git add -A     # .gitignore 는 그대로 존중
    tree=$(git write-tree)
    snap=$(git commit-tree $tree -p HEAD)

만든 커밋은 `refs/rondo/snap/<ns>` 에 매달아 gc 가 걷어가지 않게 한다. 이 ref 는 로컬 전용이라
`git log` 에도 안 보이고 push 되지도 않는다.

## 되돌리는 법

스냅샷 트리로 강제 체크아웃하지 않는다. 그러면 스냅샷 이후에 생긴 파일이 남는다.
지금 상태도 스냅샷으로 굳힌 뒤 **두 스냅샷의 diff 를 역적용**한다. 생성·삭제·수정이 모두 잡힌다.

되돌리기 직전 상태도 스냅샷으로 남으므로 undo 자체를 다시 undo 할 수 있다.

**커밋은 건드리지 않는다.** 작업 트리만 되돌린다.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .gitcmd import GitError, git

REF_PREFIX = "refs/rondo/snap"
KEEP = 20


@dataclass(frozen=True)
class Snap:
    ref: str
    sha: str
    at: float
    label: str

    @property
    def short(self) -> str:
        return self.sha[:8]


def _head(root: Path) -> str | None:
    try:
        return git(root, "rev-parse", "HEAD").strip()
    except GitError:
        return None  # 커밋이 하나도 없는 레포


def snapshot(root: Path, label: str = "") -> Snap:
    """지금 작업 트리를 커밋 객체 하나로 굳힌다. 트리·인덱스·브랜치는 안 건드린다."""
    stamp = time.time()
    with tempfile.TemporaryDirectory() as workspace:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(workspace) / "index"))
        for args in (("add", "-A"), ("write-tree",)):
            done = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, env=env, timeout=120,
            )
            if done.returncode != 0:
                raise GitError(f"snapshot 실패: {done.stderr.strip()}")
            tree = done.stdout.strip()

    parent = _head(root)
    commit_args = ["commit-tree", tree, "-m", label or "rondo snapshot"]
    if parent:
        commit_args += ["-p", parent]
    sha = git(root, *commit_args).strip()

    ref = f"{REF_PREFIX}/{time.time_ns()}"
    git(root, "update-ref", ref, sha, "-m", label or "rondo snapshot")
    prune(root)
    return Snap(ref=ref, sha=sha, at=stamp, label=label)


def snapshots(root: Path) -> list[Snap]:
    """최신이 먼저."""
    rows = git(
        root, "for-each-ref", "--sort=-refname",
        "--format=%(refname) %(objectname) %(contents:subject)", REF_PREFIX,
        check=False,
    )
    found = []
    for line in rows.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        ref, sha = parts[0], parts[1]
        label = parts[2] if len(parts) > 2 else ""
        try:
            when = float(ref.rsplit("/", 1)[1]) / 1e9
        except ValueError:
            when = 0.0
        found.append(Snap(ref=ref, sha=sha, at=when, label=label))
    return found


def prune(root: Path, keep: int = KEEP) -> int:
    dropped = snapshots(root)[keep:]
    for snap in dropped:
        git(root, "update-ref", "-d", snap.ref, check=False)
    return len(dropped)


def dirty_against(root: Path, snap: Snap) -> bool:
    """스냅샷 이후 실제로 바뀐 게 있나."""
    current = snapshot(root, "rondo undo 검사")
    changed = bool(git(root, "diff", "--name-only", snap.sha, current.sha).strip())
    git(root, "update-ref", "-d", current.ref, check=False)  # 검사용은 남기지 않는다
    return changed


def undo(root: Path, steps: int = 1) -> dict:
    """작업 트리를 steps 개 전 스냅샷 시점으로 되돌린다. 커밋은 건드리지 않는다."""
    history = snapshots(root)
    if len(history) < steps:
        raise GitError("되돌릴 스냅샷이 없습니다")
    target = history[steps - 1]

    # 되돌리기 직전 상태를 남긴다 — undo 를 다시 undo 할 수 있어야 한다
    before = snapshot(root, "rondo undo 직전")

    patch = git(root, "diff", "--binary", target.sha, before.sha)
    if not patch.strip():
        return {"undone": False, "target": target.short, "reason": "바뀐 것이 없습니다"}

    done = subprocess.run(
        ["git", "-C", str(root), "apply", "-R", "--whitespace=nowarn", "-"],
        input=patch, capture_output=True, text=True, timeout=120,
    )
    if done.returncode != 0:
        raise GitError(
            f"되돌리지 못했습니다: {done.stderr.strip()}\n"
            f"직전 상태는 {before.short} 로 남겨두었습니다."
        )
    return {"undone": True, "target": target.short, "before": before.short}
