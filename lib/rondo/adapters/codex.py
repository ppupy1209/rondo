"""Codex CLI 어댑터.

읽는 곳 (둘 다 문서화되지 않은 내부다 — 여기 말고 다른 데서 알면 안 된다):

  ~/.codex/state_5.sqlite      threads 테이블. 모델·reasoning effort
  ~/.codex/sessions/**/*.jsonl rollout 로그. rate_limits 스냅샷

주의할 점 두 가지가 실제로 물렸던 자리다.
  - state_5.sqlite 는 WAL 이다. immutable=1 로 먼저 열면 -wal 을 통째로 무시해
    방금 만든 세션이 안 보인다. mode=ro 를 먼저 쓰고 잠겼을 때만 물러선다.
  - threads 에는 서브에이전트(auto-review 등) 행이 섞인다. thread_source='user'.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..model import Check, Snapshot, Window
from .base import Adapter

STATE_DB = Path.home() / ".codex" / "state_5.sqlite"
SESSIONS = Path.home() / ".codex" / "sessions"
TAIL_BYTES = 400_000
RATE_KEY = '"rate_limits":'


def _query(path: Path, sql: str, args: tuple = ()) -> tuple | None:
    if not path.exists():
        return None
    for mode in ("mode=ro", "immutable=1"):
        try:
            con = sqlite3.connect(f"file:{path}?{mode}", uri=True, timeout=1)
            row = con.execute(sql, args).fetchone()
            con.close()
            return row
        except sqlite3.Error:
            continue
    return None


def newest_rollout() -> Path | None:
    """sessions/<년>/<월>/<일>/*.jsonl 중 가장 최근 파일."""
    path = SESSIONS
    try:
        for _ in range(3):
            names = sorted(p.name for p in path.iterdir())
            if not names:
                return None
            path = path / names[-1]
        files = [p for p in path.iterdir() if p.suffix == ".jsonl"]
    except OSError:
        return None
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _label(window_minutes: int) -> str:
    if window_minutes >= 10080:
        return "wk"
    if window_minutes >= 60:
        return f"{window_minutes // 60}h"
    return f"{window_minutes}m"


def read_limits() -> tuple[list[Window], str | None]:
    """rollout 꼬리에서 마지막 rate_limits 스냅샷. 한도는 계정 단위라 레포를 안 따진다."""
    path = newest_rollout()
    if path is None:
        return [], "rollout 로그 없음"
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            blob = fh.read().decode("utf-8", "replace")
    except OSError as exc:
        return [], f"rollout 읽기 실패: {exc}"

    at = blob.rfind(RATE_KEY)
    if at < 0:
        return [], "rollout 에 rate_limits 없음 — 스키마 변경 가능"
    try:
        # 값 앞의 공백은 raw_decode 가 못 넘긴다. 지금 codex 는 compact 로 쓰지만
        # 거기에 기대지 않는다.
        snapshot, _ = json.JSONDecoder().raw_decode(blob[at + len(RATE_KEY):].lstrip())
    except ValueError:
        return [], "rate_limits 파싱 실패 — 스키마 변경 가능"

    windows = []
    for slot in ("secondary", "primary"):  # 짧은 창을 앞에
        window = snapshot.get(slot)
        if not window:
            continue
        try:
            windows.append(
                Window(
                    label=_label(int(window.get("window_minutes") or 0)),
                    remaining=100.0 - float(window["used_percent"]),
                    resets_at=float(window["resets_at"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return windows, "rate_limits 필드 모양이 다름 — 스키마 변경 가능"
    return windows, None


class CodexAdapter(Adapter):
    name = "codex"
    binary = "codex"
    pane_command = "codex-session"
    capabilities = ("model", "limits")

    def snapshot(self, root: Path) -> Snapshot:
        row = _query(
            STATE_DB,
            "SELECT model, reasoning_effort FROM threads "
            "WHERE cwd = ? AND thread_source = 'user' ORDER BY updated_at_ms DESC LIMIT 1",
            (str(root),),
        )
        model = None
        if row:
            model, effort = row
            if effort:
                model = f"{model} {effort}"

        windows, error = read_limits()
        return Snapshot(
            agent=self.name,
            model=model,
            windows=windows,
            source="state_5.sqlite + rollout",
            error=error if not windows and model is None else None,
        )

    def diagnose(self, root: Path) -> list[Check]:
        if not self.installed():
            return [Check(c, False, "codex 미설치") for c in self.capabilities]

        checks = []
        row = _query(STATE_DB, "SELECT count(*) FROM threads WHERE thread_source = 'user'")
        if row is None:
            checks.append(Check("model", False, f"{STATE_DB.name} 를 못 읽음"))
        elif not row[0]:
            checks.append(Check("model", False, "user 스레드가 아직 없음"))
        else:
            snap = self.snapshot(root)
            checks.append(
                Check("model", snap.model is not None,
                      "threads.model" if snap.model else "이 레포의 스레드 없음")
            )

        windows, error = read_limits()
        checks.append(
            Check("limits", bool(windows), error or f"rollout rate_limits · {len(windows)}개 창")
        )
        return checks
