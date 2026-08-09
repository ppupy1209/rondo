"""Gemini (Antigravity CLI, `agy`) 어댑터.

두 출처가 성격이 완전히 다르다.

  모델   ~/.gemini/antigravity-cli/conversations/*.db
         SQLite 인데 내용이 protobuf blob 이라 모델명 문자열만 긁는다.
  한도   `agy -p "/usage"` 출력
         한도는 디스크에 안 남는다 — quota_manager 가 실행 중에 받아 메모리에만 둔다.
         print 모드에서 슬래시 커맨드가 먹는 점을 이용해 직접 물어본다.

`/usage` 호출은 8초쯤 걸린다. 5초 루프에서 그대로 부르면 화면이 멈추므로 캐시를 두고
백그라운드 스레드로만 갱신한다.

출력은 남은 비율을 바로 준다. 다른 벤더(used%)와 달리 뒤집지 않는다.

    Gemini Models\tWeekly Limit Remaining\t99%\t2026-08-10T06:07:01Z
"""
from __future__ import annotations

import calendar
import re
import subprocess
import threading
import time
from pathlib import Path

from ..model import Check, Snapshot, Window
from ..paths import CACHE, atomic_json, read_json
from .base import Adapter

CONVERSATIONS = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
USAGE_CACHE = CACHE / "gemini-usage.json"
REFRESH_SECONDS = 600
USAGE_TIMEOUT = 120
MODEL_PATTERN = re.compile(rb"gemini-[0-9a-z.\-]+")
ROW_LABELS = (("Five Hour", "5h"), ("Weekly", "wk"))

_refresh_lock = threading.Lock()


def read_model() -> str | None:
    # ponytail: protobuf blob 이라 문자열 스캔이다. agy 가 평문 필드를 노출하면 교체.
    try:
        databases = [p for p in CONVERSATIONS.iterdir() if p.suffix == ".db"]
    except OSError:
        return None
    if not databases:
        return None
    try:
        blob = max(databases, key=lambda p: p.stat().st_mtime).read_bytes()
    except OSError:
        return None
    names = MODEL_PATTERN.findall(blob)
    # 같은 계열 이름이 여럿 박혀 있다. 가장 구체적인 것(긴 것)을 쓴다.
    return max((n.decode() for n in names), key=len) if names else None


def parse_usage(output: str) -> dict[str, dict]:
    """`agy -p /usage` 출력 -> {label: {remaining, resets_at}}.

    Claude·GPT 모델 행도 같이 나오지만 이 패널이 쓰는 건 Gemini 모델이라 그 행만 본다.
    """
    windows: dict[str, dict] = {}
    for row in output.splitlines():
        columns = [c.strip() for c in row.split("\t")]
        if len(columns) < 4 or not columns[0].startswith("Gemini"):
            continue
        label = next((tag for needle, tag in ROW_LABELS if needle in columns[1]), None)
        if label is None:
            continue
        try:
            remaining = float(columns[2].rstrip("%"))
            # 출력은 UTC(Z). timegm 이라야 로컬 타임존·DST 에 안 흔들린다.
            resets_at = calendar.timegm(time.strptime(columns[3], "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            continue
        windows[label] = {"remaining": remaining, "resets_at": resets_at}
    return windows


def refresh_usage() -> None:
    """agy 를 실제로 불러 캐시를 채운다. 호출자가 백그라운드에서 돌린다."""
    try:
        done = subprocess.run(
            ["agy", "-p", "/usage"], capture_output=True, text=True, timeout=USAGE_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return
    windows = parse_usage(done.stdout)
    if not windows:  # 빈 결과로 멀쩡한 캐시를 덮지 않는다
        return
    try:
        atomic_json(USAGE_CACHE, {"windows": windows, "at": int(time.time())})
    except OSError:
        pass


def cached_usage(refresh: bool = True) -> list[Window]:
    """캐시된 한도. 오래됐으면 갱신을 백그라운드로 걸고 지금 값은 그대로 돌려준다."""
    cached = read_json(USAGE_CACHE)
    if refresh and time.time() - cached.get("at", 0) > REFRESH_SECONDS and not _refresh_lock.locked():
        def worker() -> None:
            with _refresh_lock:
                refresh_usage()

        threading.Thread(target=worker, daemon=True).start()

    now = time.time()
    windows = []
    for label in ("5h", "wk"):
        window = (cached.get("windows") or {}).get(label) or {}
        # remaining 이 표준. used_percentage 는 예전 캐시 형식이라 함께 받아준다.
        if "remaining" in window:
            remaining = float(window["remaining"])
        elif "used_percentage" in window:
            remaining = 100.0 - float(window["used_percentage"])
        else:
            continue
        resets_at = float(window.get("resets_at") or 0)
        if resets_at > now:
            windows.append(Window(label=label, remaining=remaining, resets_at=resets_at))
    return windows


class GeminiAdapter(Adapter):
    name = "gemini"
    binary = "agy"
    pane_command = "agy-session"
    capabilities = ("model", "limits")

    def snapshot(self, root: Path) -> Snapshot:
        model = read_model()
        windows = cached_usage()
        error = None
        if model is None and not windows:
            error = "대화 기록 없음 — agy 패널에서 한 번 작업해야 채워진다"
        return Snapshot(
            agent=self.name,
            model=model,
            windows=windows,
            source="conversations/*.db + agy -p /usage",
            error=error,
        )

    def diagnose(self, root: Path) -> list[Check]:
        if not self.installed():
            return [Check(c, False, "agy 미설치") for c in self.capabilities]
        model = read_model()
        windows = cached_usage(refresh=False)
        cached = read_json(USAGE_CACHE)
        age = int(time.time() - cached.get("at", 0)) if cached else None
        return [
            Check("model", model is not None,
                  "conversations/*.db" if model else "대화 기록 없음 — 한 번 작업해야 생긴다"),
            Check("limits", bool(windows),
                  f"agy -p /usage 캐시 · {age}초 전" if windows
                  else "usage 캐시 없음 — 최대 10분 뒤 채워진다"),
        ]
