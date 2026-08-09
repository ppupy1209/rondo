"""Small, dependency-free lifecycle for managed Rondo installations."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .paths import atomic_json

REPOSITORY = "ppupy1209/rondo"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MARKER = ".rondo-release.json"
VERSION = re.compile(r"(?:v)?([0-9]+)\.([0-9]+)\.([0-9]+)")
MAX_RESPONSE = 1_000_000


class ReleaseError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def normalize_version(value: str) -> str:
    match = VERSION.fullmatch(value.strip())
    if not match:
        raise ReleaseError("invalid_version")
    return ".".join(match.groups())


def version_tuple(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in normalize_version(value).split("."))


def metadata(root: Path) -> dict:
    target = root / MARKER
    if root.is_symlink() or target.is_symlink() or not target.is_file():
        raise ReleaseError("unmanaged")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        version = normalize_version(value["version"])
    except (OSError, ValueError, KeyError, TypeError, ReleaseError):
        raise ReleaseError("state_unsafe") from None
    if value.get("schema") != 1:
        raise ReleaseError("state_unsafe")
    return {"schema": 1, "version": version, "source": str(value.get("source") or "release")}


def latest_version(opener=urllib.request.urlopen) -> str:
    request = urllib.request.Request(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "rondo-update"},
    )
    try:
        with opener(request, timeout=10) as response:
            payload = response.read(MAX_RESPONSE + 1)
    except (OSError, urllib.error.URLError) as error:
        raise ReleaseError("network") from error
    if len(payload) > MAX_RESPONSE:
        raise ReleaseError("invalid_release")
    try:
        value = json.loads(payload.decode("utf-8"))
        return normalize_version(value["tag_name"])
    except (UnicodeError, ValueError, KeyError, TypeError, ReleaseError):
        raise ReleaseError("invalid_release") from None


def update(root: Path, target: str, runner=subprocess.run) -> str:
    current = metadata(root)["version"]
    target = normalize_version(target)
    if version_tuple(target) < version_tuple(current):
        raise ReleaseError("use_rollback")
    if target == current:
        return current
    environment = os.environ.copy()
    environment.update({"RONDO_FORCE_REMOTE": "1", "RONDO_VERSION": target})
    if os.name == "nt":
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(root / "install.ps1"), "-Version", target, "-ForceRemote",
        ]
    else:
        command = ["sh", str(root / "install.sh")]
    try:
        runner(command, check=True, env=environment)
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseError("install_failed") from error
    installed = metadata(root)["version"]
    if installed != target:
        raise ReleaseError("install_failed")
    return installed


def rollback(root: Path) -> tuple[str, str]:
    current = metadata(root)["version"]
    previous = root.with_name(root.name + ".previous")
    if not previous.exists():
        raise ReleaseError("no_previous")
    restored = metadata(previous)["version"]
    swap = root.with_name(f".{root.name}.rollback-{os.getpid()}")
    if previous.parent != root.parent or swap.exists() or previous.is_symlink():
        raise ReleaseError("state_unsafe")
    root.replace(swap)
    try:
        previous.replace(root)
        swap.replace(previous)
    except OSError as error:
        try:
            if root.exists() and not previous.exists() and swap.exists():
                root.replace(previous)
            if not root.exists() and swap.exists():
                swap.replace(root)
        except OSError:
            pass
        raise ReleaseError("rollback_failed") from error
    return current, restored


def _remove_hooks(settings: list[Path]) -> None:
    for target in settings:
        if target.is_symlink() or not target.is_file():
            continue
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        changed = False
        hooks = value.get("hooks")
        if isinstance(hooks, dict):
            for event in list(hooks):
                groups = hooks[event]
                if not isinstance(groups, list):
                    continue
                kept_groups = []
                for group in groups:
                    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                        kept_groups.append(group)
                        continue
                    entries = [
                        entry for entry in group["hooks"]
                        if not (
                            isinstance(entry, dict)
                            and isinstance(entry.get("command"), str)
                            and (
                                entry["command"] == "rondo snap --auto"
                                or entry["command"] in {"handoff Claude", "handoff Gemini"}
                            )
                        )
                    ]
                    if len(entries) != len(group["hooks"]):
                        changed = True
                    if entries:
                        kept_groups.append(group | {"hooks": entries})
                if kept_groups:
                    hooks[event] = kept_groups
                else:
                    hooks.pop(event)
            if not hooks:
                value.pop("hooks", None)
        status = value.get("statusLine")
        if isinstance(status, dict) and status.get("command") in {
            "rondo-claude-status", "claude-statusline",
        }:
            value.pop("statusLine")
            changed = True
        if changed:
            backup = target.with_suffix(target.suffix + ".rondo-uninstall.bak")
            if not backup.exists():
                shutil.copy2(target, backup)
            atomic_json(target, value)


def _launchers(root: Path, binary_directory: Path) -> list[Path]:
    removed = []
    if not binary_directory.is_dir() or binary_directory.is_symlink():
        return removed
    source_directory = root / "bin"
    if source_directory.is_symlink() or not source_directory.is_dir():
        raise ReleaseError("state_unsafe")
    try:
        sources = {
            path.name: path.resolve()
            for path in source_directory.iterdir()
            if path.is_file() and not path.is_symlink()
        }
    except OSError as error:
        raise ReleaseError("state_unsafe") from error
    for name, source in sources.items():
        target = binary_directory / name
        try:
            if target.is_symlink() and target.resolve() == source:
                target.unlink()
                removed.append(target)
        except OSError:
            continue
    if os.name == "nt":
        expected = str(root).casefold()
        names = {
            "rondo", "ai", "ai-status", "rondo-status", "rondo-claude-status",
            "claude-statusline", "rondo-lens", "rondo-relay", "rondo-agent-session",
            "claude-session", "codex-session", "agy-session", "kimi-session",
            "grok-session",
        }
        for name in names:
            target = binary_directory / f"{name}.cmd"
            try:
                if target.is_file() and expected in target.read_text(encoding="utf-8").casefold():
                    target.unlink()
                    removed.append(target)
            except OSError:
                continue
    return removed


def _remove_windows_path(binary_directory: Path) -> None:
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
        ) as key:
            value, kind = winreg.QueryValueEx(key, "Path")
            paths = [part for part in value.split(";") if part and Path(part) != binary_directory]
            winreg.SetValueEx(key, "Path", 0, kind, ";".join(paths))
    except (OSError, ImportError):
        pass


def uninstall(
    root: Path,
    binary_directory: Path,
    settings: list[Path],
    config: Path,
    cache: Path,
    purge: bool = False,
) -> dict:
    version = metadata(root)["version"]
    if root.parent == root or len(root.parts) < 3:
        raise ReleaseError("state_unsafe")
    previous = root.with_name(root.name + ".previous")
    removing = root.with_name(f".{root.name}.uninstall-{os.getpid()}")
    if removing.exists() or previous.is_symlink():
        raise ReleaseError("state_unsafe")
    if previous.exists():
        metadata(previous)
    purge_targets: list[Path] = []
    if purge:
        for directory in (config, cache):
            if directory.is_symlink() or len(directory.parts) < 3:
                raise ReleaseError("state_unsafe")
            if directory.exists() and not directory.is_dir():
                raise ReleaseError("state_unsafe")
            purge_targets.append(directory)

    # Everything that can make the operation fail closed is checked before the
    # first user-visible mutation. Hooks and launchers are removed only after
    # the exact managed installation has passed validation.
    removed_launchers = _launchers(root, binary_directory)
    _remove_hooks(settings)
    _remove_windows_path(binary_directory)
    root.replace(removing)
    shutil.rmtree(removing)
    if previous.is_dir():
        shutil.rmtree(previous)
    for directory in purge_targets:
        if directory.is_dir():
            shutil.rmtree(directory)
    return {"version": version, "launchers": len(removed_launchers), "purged": purge}


def installation_root(script: str | Path) -> Path:
    return Path(script).resolve().parent.parent
