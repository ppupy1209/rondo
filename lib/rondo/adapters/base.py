"""어댑터 공통 뼈대.

어댑터 하나가 벤더 하나의 로컬 저장 형식을 전부 안다. 다른 코드는 벤더 경로도,
스키마도, 필드 이름도 몰라야 한다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..model import Check, Snapshot


class Adapter:
    name = ""           # rondo 안에서 쓰는 이름 (패널 이름과 같다)
    binary = ""         # PATH 에서 찾을 실행 파일
    pane_command = ""   # 패널에서 띄울 명령 (보통 *-session 래퍼)
    capabilities: tuple[str, ...] = ()   # "model" | "limits" | "transcript"

    def installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def version(self) -> str | None:
        """벤더 CLI 버전. 지문으로 쓰므로 실패해도 예외를 던지지 않는다."""
        if not self.installed():
            return None
        try:
            out = subprocess.run(
                [self.binary, "--version"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip().splitlines()[0] if out.stdout.strip() else None

    def snapshot(self, root: Path) -> Snapshot:
        """지금 상태. 읽기 실패는 예외 대신 Snapshot.error 로 알린다."""
        return Snapshot(agent=self.name, error="not implemented")

    def diagnose(self, root: Path) -> list[Check]:
        """capability 별로 지금 실제 읽히는지. `rondo doctor --deep` 이 쓴다.

        기본 구현은 snapshot 결과로 판정한다. 벤더별로 더 정확히 짚을 수 있으면
        어댑터에서 덮어쓴다.
        """
        if not self.installed():
            return [Check(c, False, f"{self.binary} 미설치") for c in self.capabilities]
        snap = self.snapshot(root)
        checks = []
        for capability in self.capabilities:
            if capability == "model":
                ok = snap.model is not None
            elif capability == "limits":
                ok = bool(snap.live_windows())
            else:
                ok = snap.error is None
            checks.append(Check(capability, ok, snap.source if ok else (snap.error or "값 없음")))
        return checks
