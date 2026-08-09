"""어댑터 레지스트리 + 벤더 버전 지문.

지문이 있는 이유: 벤더 CLI 가 올라가면서 내부 스키마가 바뀌면 지금까지는 화면에
'-' 만 뜨고 사용자는 이유를 몰랐다. 버전이 바뀐 것을 감지하면 capability 를 다시
검사하고, 되던 게 안 되면 그 사실을 말한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .adapters import Adapter, ClaudeAdapter, CodexAdapter, GeminiAdapter
from .model import Check

from .paths import CACHE

FINGERPRINT = CACHE / "adapters.json"

_ADAPTERS: dict[str, Adapter] = {
    a.name: a for a in (ClaudeAdapter(), CodexAdapter(), GeminiAdapter())
}


def get(name: str) -> Adapter | None:
    return _ADAPTERS.get(name)


def all_adapters() -> list[Adapter]:
    return list(_ADAPTERS.values())


def _load() -> dict:
    try:
        return json.loads(FINGERPRINT.read_text())
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = FINGERPRINT.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(FINGERPRINT)
    except OSError:
        pass


def check_fingerprint(adapter: Adapter, root: Path) -> list[str]:
    """벤더 버전이 바뀌었으면 다시 검사하고, 되던 capability 가 깨졌으면 알린다.

    돌려주는 값은 사용자에게 보여줄 경고 문장. 없으면 빈 리스트.
    """
    version = adapter.version()
    store = _load()
    previous = store.get(adapter.name, {})
    checks = {c.capability: c for c in adapter.diagnose(root)}
    current = {"version": version, "ok": sorted(k for k, c in checks.items() if c.ok)}

    warnings = []
    if previous.get("version") and previous["version"] != version:
        lost = set(previous.get("ok", [])) - set(current["ok"])
        for capability in sorted(lost):
            # 어댑터에서 아예 사라진 capability 일 수도 있다. 진단이 죽으면 안 된다.
            check = checks.get(capability)
            detail = check.detail if check else "이 버전에는 해당 항목이 없습니다"
            warnings.append(
                f"{adapter.name} {previous['version']} → {version}: "
                f"'{capability}' 를 더 못 읽습니다 ({detail})"
            )

    if previous != current:
        store[adapter.name] = current
        _save(store)
    return warnings


def diagnose_all(root: Path) -> dict[str, list[Check]]:
    return {a.name: a.diagnose(root) for a in all_adapters()}
