"""경로와 설정 읽기. 스크립트마다 따로 갖고 있던 것을 한곳으로 모은다."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "rondo"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "rondo"


def repo_key(project: str | Path) -> str:
    """프로젝트 경로 -> 캐시 파일 이름. 이름이 같은 다른 레포와 안 섞이게 해시를 쓴다."""
    return hashlib.sha256(str(Path(project).resolve()).encode()).hexdigest()[:16]


def setting(name: str, default: str = "") -> str:
    try:
        return (CONFIG / name).read_text().strip()
    except OSError:
        return default


def atomic_json(path: Path, data: dict) -> None:
    """부분 기록된 JSON 을 읽는 일이 없도록 임시 파일에 쓰고 갈아끼운다."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
