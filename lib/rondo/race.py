"""rondo race — 같은 과제를 에이전트마다 격리된 worktree 에서 돌리고 하나를 고른다.

여기는 git 부분만 한다. 패널 생성·프롬프트 투입은 bin/rondo 가 맡는다.
순수하게 파일과 git 만 다루므로 임시 레포로 전부 테스트할 수 있다.

설계 배경은 docs/race.md.
"""
from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .gitcmd import GitError, git
from .paths import CACHE, atomic_json, read_json, repo_key

BRANCH_PREFIX = "rondo/race"
DEFAULT_THRESHOLD = 10.0  # 남은 한도가 이 % 미만이면 참가시키지 않는다


# race 가 던지는 오류와 git 오류를 호출부에서 구분할 이유가 없다.
RaceError = GitError


@dataclass
class Race:
    root: Path
    run_id: str
    task: str
    base: str
    started_at: float
    agents: dict[str, Path] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "root": str(self.root),
            "run_id": self.run_id,
            "task": self.task,
            "base": self.base,
            "started_at": self.started_at,
            "agents": {name: str(path) for name, path in self.agents.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> "Race":
        return cls(
            root=Path(data["root"]),
            run_id=data["run_id"],
            task=data["task"],
            base=data["base"],
            started_at=float(data.get("started_at") or 0),
            agents={name: Path(p) for name, p in (data.get("agents") or {}).items()},
        )


def race_home(root: Path) -> Path:
    return CACHE / "race" / repo_key(root)


def state_path(root: Path) -> Path:
    return race_home(root) / "current.json"


def load(root: Path) -> Race | None:
    data = read_json(state_path(root))
    return Race.from_json(data) if data else None


def eligible(snapshots: dict, threshold: float = DEFAULT_THRESHOLD) -> tuple[list[str], dict[str, str]]:
    """한도가 남은 에이전트만 고른다.

    한도를 못 읽는 에이전트(kimi·grok 등)는 막을 근거가 없으니 통과시킨다.
    돌려주는 값은 (참가자, {제외된 에이전트: 이유}).
    """
    joining, skipped = [], {}
    for name, snapshot in snapshots.items():
        windows = snapshot.live_windows() if snapshot else []
        if not windows:
            joining.append(name)
            continue
        tightest = min(windows, key=lambda w: w.remaining)
        if tightest.remaining < threshold:
            skipped[name] = f"{tightest.label} {tightest.remaining:.0f}% 남음"
        else:
            joining.append(name)
    return joining, skipped


def freeze_base(root: Path) -> str:
    """지금 트리 상태를 커밋 객체 하나로 굳힌다.

    `git stash create` 는 stash 목록에 넣지도, 작업 트리를 건드리지도 않는다. 객체만 만든다.
    커밋 안 된 변경이 있어도 사용자를 막지 않으려고 이걸 쓴다.
    """
    stashed = git(root, "stash", "create").strip()
    return stashed or git(root, "rev-parse", "HEAD").strip()


def start(root: Path, task: str, agents: list[str]) -> Race:
    """참가자마다 worktree 를 만들고 상태를 기록한다. 패널은 호출자가 띄운다."""
    if not agents:
        raise RaceError("참가할 에이전트가 없습니다")
    if load(root) is not None:
        raise RaceError("이미 진행 중인 race 가 있습니다. rondo take 또는 rondo race --abort")

    race = Race(
        root=root,
        run_id=uuid.uuid4().hex[:8],
        task=task,
        base=freeze_base(root),
        started_at=time.time(),
    )

    made: list[Path] = []
    try:
        for agent in agents:
            # 레포 밖에 만든다. 안에 두면 에이전트가 자기 worktree 를 소스로 착각한다.
            path = race_home(root) / race.run_id / agent
            path.parent.mkdir(parents=True, exist_ok=True)
            # git worktree list 는 심볼릭 링크를 푼 경로를 준다(macOS 의 /var -> /private/var).
            # 여기서 맞춰두지 않으면 살아 있는 race 를 고아로 보고 prune 이 지운다.
            path = path.resolve()
            git(root, "worktree", "add", "-b",
                f"{BRANCH_PREFIX}/{race.run_id}/{agent}", str(path), race.base)
            made.append(path)
            race.agents[agent] = path
    except RaceError:
        for path in made:  # 절반만 만들어진 상태를 남기지 않는다
            _remove_worktree(root, path)
        raise

    atomic_json(state_path(root), race.to_json())
    return race


def _numstat(race: Race, agent: str) -> tuple[int, int, int]:
    """(파일 수, 추가 줄, 삭제 줄). 에이전트는 대개 커밋하지 않아 작업 트리를 본다."""
    worktree = race.agents[agent]
    # -N(intent-to-add) 이라야 새 파일도 diff 에 잡힌다. 인덱스는 worktree 것이라 버려도 된다.
    git(worktree, "add", "-A", "-N", check=False)
    files = added = removed = 0
    for row in git(worktree, "diff", "--numstat", race.base).splitlines():
        columns = row.split("\t")
        if len(columns) < 3:
            continue
        files += 1
        # 바이너리는 "-" 로 나온다
        added += int(columns[0]) if columns[0].isdigit() else 0
        removed += int(columns[1]) if columns[1].isdigit() else 0
    return files, added, removed


def summary(race: Race) -> list[dict]:
    rows = []
    for agent in race.agents:
        try:
            files, added, removed = _numstat(race, agent)
            rows.append({"agent": agent, "files": files, "added": added, "removed": removed})
        except RaceError as exc:
            rows.append({"agent": agent, "error": str(exc)})
    return rows


def patch_of(race: Race, agent: str) -> str:
    """채택·보관에 쓸 patch. 새 파일과 바이너리까지 포함한다."""
    worktree = race.agents[agent]
    git(worktree, "add", "-A", check=False)
    return git(worktree, "diff", "--cached", "--binary", race.base)


def diff_text(race: Race, agent: str) -> str:
    if agent not in race.agents:
        raise RaceError(f"race 에 없는 에이전트: {agent}")
    return patch_of(race, agent)


def _save_patch(race: Race, agent: str, patch: str) -> Path:
    """worktree 를 지우기 전에 남긴다. 잘못 눌러도 복구할 수 있어야 한다."""
    target = race_home(race.root) / "patches" / f"{race.run_id}-{agent}.patch"
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_text(patch)
    return target


def _remove_worktree(root: Path, path: Path) -> None:
    git(root, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _cleanup(race: Race) -> None:
    for agent, path in race.agents.items():
        _remove_worktree(race.root, path)
        git(race.root, "branch", "-D", f"{BRANCH_PREFIX}/{race.run_id}/{agent}", check=False)
    git(race.root, "worktree", "prune", check=False)
    run_dir = race_home(race.root) / race.run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    state_path(race.root).unlink(missing_ok=True)


def take(race: Race, agent: str) -> dict:
    """고른 결과를 원본 트리에 얹는다. 커밋은 하지 않는다 — 사람이 정한다."""
    if agent not in race.agents:
        raise RaceError(f"race 에 없는 에이전트: {agent}")

    patch = patch_of(race, agent)
    saved = _save_patch(race, agent, patch)
    for other in race.agents:  # 버릴 것도 복구 가능하게 남긴다
        if other != agent:
            _save_patch(race, other, patch_of(race, other))

    if not patch.strip():
        _cleanup(race)
        return {"agent": agent, "applied": False, "patch": str(saved),
                "reason": "변경 없음"}

    # base 가 stash 객체(미커밋 상태)면 원본 인덱스는 아직 HEAD 라서 -3 가 "인덱스와 맞지
    # 않습니다" 로 거절한다. 작업 트리 기준의 평범한 apply 를 먼저 시도하고, 그게 안 될 때만
    # 3-way 로 넘어간다.
    for extra in ([], ["-3"]):
        done = subprocess.run(
            ["git", "-C", str(race.root), "apply", *extra, "--whitespace=nowarn", "-"],
            input=patch, capture_output=True, text=True, timeout=120,
        )
        if done.returncode == 0:
            break
    if done.returncode != 0:
        # 원본이 race 도중 바뀌면 여기서 걸린다. worktree 는 남겨 다시 시도할 수 있게 한다.
        raise RaceError(
            f"원본 트리에 적용하지 못했습니다: {done.stderr.strip()}\n"
            f"patch 는 {saved} 에 있습니다. race 는 그대로 두었습니다."
        )

    _cleanup(race)
    return {"agent": agent, "applied": True, "patch": str(saved)}


def abort(race: Race) -> list[str]:
    saved = []
    for agent in race.agents:
        try:
            saved.append(str(_save_patch(race, agent, patch_of(race, agent))))
        except RaceError:
            continue
    _cleanup(race)
    return saved


def orphans(root: Path) -> list[Path]:
    """상태 파일이 가리키지 않는 race worktree. rondo doctor 가 쓴다."""
    current = load(root)
    live = {str(Path(p).resolve()) for p in (current.agents.values() if current else [])}
    found = []
    for line in git(root, "worktree", "list", "--porcelain", check=False).splitlines():
        if not line.startswith("worktree "):
            continue
        path = str(Path(line.split(" ", 1)[1]).resolve())
        if f"/race/{repo_key(root)}/" in path and path not in live:
            found.append(Path(path))
    return found


def prune_orphans(root: Path) -> list[Path]:
    removed = orphans(root)
    for path in removed:
        _remove_worktree(root, path)
    git(root, "worktree", "prune", check=False)
    return removed
