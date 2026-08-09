"""어댑터가 주고받는 값. 벤더 표현을 여기서 하나로 맞춘다."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Window:
    """사용 한도 창 하나.

    벤더마다 '쓴 비율'(claude, codex)과 '남은 비율'(gemini)이 섞여 있다.
    어댑터 경계에서 전부 remaining 으로 뒤집어 들여보낸다. 화면은 남은 양만 그린다.
    """

    label: str        # "5h" | "wk" 처럼 짧은 표시용 이름
    remaining: float  # 0..100
    resets_at: float  # epoch seconds

    @property
    def expired(self) -> bool:
        return self.resets_at <= time.time()


@dataclass(frozen=True)
class Check:
    """capability 하나가 지금 실제로 동작하는지. doctor 가 그대로 출력한다."""

    capability: str
    ok: bool
    detail: str = ""


@dataclass
class Snapshot:
    """한 에이전트의 현재 상태. 못 읽은 항목은 None/빈 값이고 error 에 이유가 남는다."""

    agent: str
    model: str | None = None
    windows: list[Window] = field(default_factory=list)
    age: float = 0.0          # 바탕 데이터가 쓰인 뒤 흐른 초. 0 이면 실시간
    source: str = ""          # 어디서 읽었는지 (doctor·디버깅용)
    error: str | None = None

    def live_windows(self) -> list[Window]:
        return [w for w in self.windows if not w.expired]
