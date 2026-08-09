"""Claude Code 어댑터.

Claude 는 다른 벤더와 달리 파일을 뒤지지 않는다. CLI 가 statusLine 명령에 세션 JSON 을
직접 넘겨준다. 그 payload 가 유일한 입구다.

  rate_limits.five_hour / seven_day  { used_percentage, resets_at }
  model.display_name, effort.level, workspace.project_dir, session_id, transcript_path

한도는 **계정 단위**라 공유 파일 하나에 모으고, 모델은 레포별 파일에 둔다. 예전에 한도까지
레포별로 캐시했다가 메시지를 안 보낸 레포에서 영영 안 보이는 문제가 있었다.

statusLine 은 Claude 가 화면을 그릴 때만 호출된다. 패널이 놀면 값이 낡으므로 Snapshot.age
로 나이를 같이 돌려준다.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..model import Check, Snapshot, Window
from ..paths import CACHE, atomic_json, read_json, repo_key
from .base import Adapter

LIMITS = CACHE / "claude-limits.json"
# 벤더 키 -> 표시 라벨. 세 스크립트가 제각각 쓰던 것을 여기 하나로 고정한다.
WINDOW_KEYS = (("five_hour", "5h"), ("seven_day", "wk"))
STALE_MODEL = 3600  # 이 초를 넘긴 모델 값은 안 쓴다


def project_dir(payload: dict) -> str | None:
    return (payload.get("workspace") or {}).get("project_dir") or payload.get("cwd")


def windows_from_payload(payload: dict) -> list[Window]:
    """statusLine payload 의 rate_limits 를 Window 로. 만료된 창은 뺀다."""
    return _windows(payload.get("rate_limits") or {})


def _windows(limits: dict) -> list[Window]:
    now = time.time()
    windows = []
    for key, label in WINDOW_KEYS:
        window = limits.get(key) or {}
        try:
            reset = float(window["resets_at"])
            used = float(window["used_percentage"])
        except (KeyError, TypeError, ValueError):
            continue
        if reset > now:
            windows.append(Window(label=label, remaining=100.0 - used, resets_at=reset))
    return windows


def tightest(windows: list[Window]) -> Window | None:
    """가장 빠듯한 창. 릴레이 발동 판단에 쓴다."""
    return min(windows, key=lambda w: w.remaining, default=None)


def model_from_payload(payload: dict) -> str | None:
    model = payload.get("model") or {}
    name = model.get("display_name") or model.get("id")
    if not name:
        return None
    effort = (payload.get("effort") or {}).get("level")
    return f"{name} {effort}" if effort else name


def write_cache(payload: dict) -> None:
    """statusLine 이 그릴 때마다 호출. 한도는 공유 파일, 모델은 레포별 파일."""
    project = project_dir(payload)
    if not project:
        return
    limits = payload.get("rate_limits") or {}
    if limits:  # 빈 값으로 덮으면 이미 받아둔 한도가 사라진다
        atomic_json(LIMITS, {"rate_limits": limits, "at": int(time.time())})
    atomic_json(
        CACHE / f"claude.{repo_key(project)}.json",
        {
            "project": project,
            "model": model_from_payload(payload),
            "at": int(time.time()),
        },
    )


def cached_limits() -> tuple[list[Window], float]:
    """(살아 있는 창, 캐시가 쓰인 뒤 흐른 초)."""
    cached = read_json(LIMITS)
    if not cached:
        return [], 0.0
    return _windows(cached.get("rate_limits") or {}), max(
        0.0, time.time() - float(cached.get("at") or time.time())
    )


class ClaudeAdapter(Adapter):
    name = "claude"
    binary = "claude"
    pane_command = "claude"
    capabilities = ("model", "limits")

    def snapshot(self, root: Path) -> Snapshot:
        windows, age = cached_limits()
        cached = read_json(CACHE / f"claude.{repo_key(root)}.json")
        model = None
        if cached.get("project") == str(root) and time.time() - (cached.get("at") or 0) <= STALE_MODEL:
            model = cached.get("model")

        error = None
        if model is None and not windows:
            error = "statusLine 캐시 없음 — Claude 패널을 한 번 띄워야 채워진다"
        return Snapshot(
            agent=self.name,
            model=model,
            windows=windows,
            age=age,
            source=str(LIMITS.name),
            error=error,
        )

    def diagnose(self, root: Path) -> list[Check]:
        if not self.installed():
            return [Check(c, False, "claude 미설치") for c in self.capabilities]
        snap = self.snapshot(root)
        windows, age = cached_limits()
        return [
            Check("model", snap.model is not None,
                  "statusLine 캐시" if snap.model else "이 레포의 캐시 없음/오래됨"),
            Check("limits", bool(windows),
                  f"{len(windows)}개 창 · {int(age)}초 전"
                  if windows else "rate_limits 없음 — 구독 계정으로 메시지를 한 번 보내야 실린다"),
        ]
