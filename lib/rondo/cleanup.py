"""Conservatively remove only global settings installed by Rondo 0.14.x."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Tuple


LEGACY_COMMANDS = {
    "rondo snap --auto",
    "handoff claude",
    "handoff gemini",
    "rondo-claude-status",
    "rondo-claude-status.cmd",
    "claude-statusline",
    "claude-statusline.cmd",
}
DROP = object()


def unsafe_path(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def normalized_command(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().replace("\\", "/").split()).lower()
    first, separator, rest = text.partition(" ")
    first = first.rsplit("/", 1)[-1]
    return first + (separator + rest if separator else "")


def _clean(value: Any) -> Tuple[Any, int]:
    if isinstance(value, dict):
        if normalized_command(value.get("command")) in LEGACY_COMMANDS:
            return DROP, 1
        result = {}
        removed = 0
        for key, child in value.items():
            cleaned, count = _clean(child)
            removed += count
            if cleaned is not DROP:
                result[key] = cleaned
        return result, removed
    if isinstance(value, list):
        result = []
        removed = 0
        for child in value:
            cleaned, count = _clean(child)
            removed += count
            if cleaned is not DROP:
                result.append(cleaned)
        return result, removed
    return value, 0


def cleanup_file(path: Path) -> int:
    if not path.exists():
        return 0
    if unsafe_path(path) or unsafe_path(path.parent) or not path.is_file():
        return 0
    try:
        # Windows PowerShell 5.1 commonly wrote the old settings file with a
        # UTF-8 BOM, so accept it while always writing clean UTF-8 afterward.
        original = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return 0
    cleaned, removed = _clean(original)
    if not removed or cleaned is DROP:
        return 0
    backup = path.with_name(path.name + ".rondo-v014.bak")
    if unsafe_path(backup) or (backup.exists() and not backup.is_file()):
        return 0
    if not backup.exists():
        shutil.copy2(str(path), str(backup))
    fd, temporary = tempfile.mkstemp(prefix=".rondo-cleanup-", dir=str(path.parent), text=True)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(cleaned, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return removed


def main() -> int:
    home = Path.home()
    paths = [home / ".claude" / "settings.json", home / ".gemini" / "settings.json"]
    removed = sum(cleanup_file(path) for path in paths)
    if removed:
        print("Removed %d legacy Rondo hook/status entries (backup kept)." % removed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
