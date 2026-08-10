#!/bin/sh
# Verified one-command bootstrap or local installer for macOS and Linux.
set -eu

RONDO_USER_HOME="${RONDO_HOME:-$HOME}"
ZELLIJ_VERSION="0.44.3"

verify_sha256() {
    python3 - "$1" "$2" "$3" <<'PY'
import hashlib, re, sys
checksums, artifact, expected_name = sys.argv[1:]
lines = []
with open(checksums, encoding="utf-8") as source:
    for line in source:
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+?)\s*", line)
        if match and match.group(2) == expected_name:
            lines.append(match.group(1).lower())
if len(lines) != 1:
    raise SystemExit("checksum entry is missing or ambiguous: " + expected_name)
digest = hashlib.sha256()
with open(artifact, "rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
if digest.hexdigest() != lines[0]:
    raise SystemExit("checksum mismatch: " + expected_name)
PY
}

verify_digest() {
    python3 - "$1" "$2" "$3" <<'PY'
import hashlib, sys
artifact, expected, name = sys.argv[1:]
digest = hashlib.sha256()
with open(artifact, "rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
if digest.hexdigest() != expected:
    raise SystemExit("checksum mismatch: " + name)
PY
}

managed_release() {
    command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
    python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null || {
        echo "Python 3.10+ is required. Install Python and run this command again." >&2
        exit 1
    }

    version="${RONDO_VERSION:-}"
    if [ -n "$version" ]; then
        version=$(python3 - "$version" <<'PY'
import re, sys
match = re.fullmatch(r"v?([0-9]+\.[0-9]+\.[0-9]+)", sys.argv[1].strip())
if not match:
    raise SystemExit("invalid RONDO_VERSION")
print(match.group(1))
PY
        )
        release_url="https://github.com/ppupy1209/rondo/releases/download/v$version"
    else
        release_url="https://github.com/ppupy1209/rondo/releases/latest/download"
    fi

    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    archive="$temporary/rondo.tar.gz"
    checksums="$temporary/SHA256SUMS"
    extracted="$temporary/extracted"
    mkdir "$extracted"
    echo "Downloading verified Rondo release..."
    curl -fsSL "$release_url/rondo.tar.gz" -o "$archive"
    curl -fsSL "$release_url/SHA256SUMS" -o "$checksums"
    verify_sha256 "$checksums" "$archive" "rondo.tar.gz"

    python3 - "$archive" "$extracted" <<'PY'
import pathlib, tarfile, sys
archive, destination = sys.argv[1:]
with tarfile.open(archive, "r:gz") as package:
    members = package.getmembers()
    if not members:
        raise SystemExit("empty Rondo archive")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit("unsafe Rondo archive")
        if not (member.isdir() or member.isfile()):
            raise SystemExit("unsupported Rondo archive entry")
    if hasattr(tarfile, "data_filter"):
        package.extractall(destination, members=members, filter="data")
    else:
        package.extractall(destination, members=members)
PY
    set -- "$extracted"/*
    if [ "$#" -ne 1 ] || [ ! -d "$1" ] || [ -L "$1" ]; then
        echo "Downloaded Rondo archive is invalid." >&2
        exit 1
    fi
    source=$1
    if [ ! -f "$source/bin/rondo" ] || [ -L "$source/bin/rondo" ]; then
        echo "Downloaded Rondo archive is invalid." >&2
        exit 1
    fi
    installed=$(python3 "$source/bin/rondo" --version | awk '{print $2}')
    if [ -n "$version" ] && [ "$installed" != "$version" ]; then
        echo "Requested Rondo $version but archive contains $installed." >&2
        exit 1
    fi
    version=$installed

    app="${RONDO_INSTALL_DIR:-$RONDO_USER_HOME/.local/share/rondo}"
    previous="$app.previous"
    staging="$app.installing"
    python3 - "$app" "$previous" "$staging" <<'PY'
import json, pathlib, re, sys
app, previous, staging = map(pathlib.Path, sys.argv[1:])
if app.parent.is_symlink() or staging.exists() or staging.is_symlink():
    raise SystemExit("refusing an unsafe or interrupted Rondo installation")
for path in (app, previous):
    if path.is_symlink():
        raise SystemExit("refusing a symlinked Rondo installation")
    if not path.exists():
        continue
    marker = path / ".rondo-release.json"
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit("refusing to replace an unmanaged Rondo directory")
    if value.get("schema") != 1 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(value.get("version", ""))):
        raise SystemExit("refusing an invalid Rondo installation")
PY
    mkdir -p "$(dirname "$app")"
    had_current=0
    if [ -d "$app" ]; then
        mv "$app" "$staging"
        had_current=1
    fi
    if ! mv "$source" "$app"; then
        [ "$had_current" -eq 0 ] || mv "$staging" "$app"
        exit 1
    fi
    python3 - "$app/.rondo-release.json" "$version" <<'PY'
import json, os, pathlib, sys
target, version = pathlib.Path(sys.argv[1]), sys.argv[2]
temporary = target.with_name(target.name + ".tmp")
temporary.write_text(json.dumps({"schema": 1, "version": version, "source": "github-release"}) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, target)
PY
    if ! RONDO_FORCE_REMOTE=0 RONDO_RELEASE_STAGED=1 sh "$app/install.sh"; then
        python3 - "$app" <<'PY'
import pathlib, shutil, sys
target = pathlib.Path(sys.argv[1])
if target.is_dir() and not target.is_symlink():
    shutil.rmtree(target)
PY
        [ "$had_current" -eq 0 ] || mv "$staging" "$app"
        exit 1
    fi
    if [ "$had_current" -eq 1 ]; then
        if ! python3 - "$previous" <<'PY'
import pathlib, shutil, sys
target = pathlib.Path(sys.argv[1])
if target.exists():
    if target.is_symlink() or len(target.parts) < 3:
        raise SystemExit("unsafe previous Rondo installation")
    shutil.rmtree(target)
PY
        then
            python3 - "$app" <<'PY'
import pathlib, shutil, sys
target = pathlib.Path(sys.argv[1])
if target.is_dir() and not target.is_symlink():
    shutil.rmtree(target)
PY
            mv "$staging" "$app"
            exit 1
        fi
        if ! mv "$staging" "$previous"; then
            python3 - "$app" <<'PY'
import pathlib, shutil, sys
target = pathlib.Path(sys.argv[1])
if target.is_dir() and not target.is_symlink():
    shutil.rmtree(target)
PY
            mv "$staging" "$app"
            exit 1
        fi
    fi
    trap - EXIT HUP INT TERM
    rm -rf "$temporary"
    exit 0
}

if [ "${RONDO_RELEASE_STAGED:-0}" != "1" ]; then
    if [ "${RONDO_FORCE_REMOTE:-0}" = "1" ]; then
        managed_release
    fi
    case "$0" in
        *install.sh) ;;
        *) managed_release ;;
    esac
fi

repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN="$RONDO_USER_HOME/.local/bin"
LAYOUTS="$RONDO_USER_HOME/.config/zellij/layouts"
SETTINGS="$RONDO_USER_HOME/.claude/settings.json"

mkdir -p "$BIN" "$LAYOUTS"

python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null || {
    echo "Python 3.10+ is required. Install Python and run this command again." >&2
    exit 1
}

if ! command -v zellij >/dev/null 2>&1 && [ ! -x "$BIN/zellij" ]; then
    command -v curl >/dev/null 2>&1 || { echo "curl is required to install Zellij" >&2; exit 1; }
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) target=aarch64-apple-darwin; zellij_sha256=b6acf83a7739cf5f0f4e9bd47709642d4d98acbbf8c34d4a12c6e706f531da61 ;;
        Darwin-x86_64) target=x86_64-apple-darwin; zellij_sha256=59f803faa32cd4e5f316f0dc2d3b7a5530a72553e38ad939286471848a418eeb ;;
        Linux-aarch64|Linux-arm64) target=aarch64-unknown-linux-musl; zellij_sha256=15e6534d42644d66973d136c590c49739dcfd6a1a2a0d3d917973f16c81b45fb ;;
        Linux-x86_64) target=x86_64-unknown-linux-musl; zellij_sha256=0f7c346788627f506c0a28296517768633cff24fc822a739f8264b640ecad751 ;;
        *) echo "Unsupported platform for automatic Zellij installation: $(uname -s) $(uname -m)" >&2; exit 1 ;;
    esac
    echo "install Zellij $ZELLIJ_VERSION (verified)"
    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    asset="zellij-$target.tar.gz"
    base="https://github.com/zellij-org/zellij/releases/download/v$ZELLIJ_VERSION"
    curl -fsSL "$base/$asset" -o "$temporary/$asset"
    verify_digest "$temporary/$asset" "$zellij_sha256" "$asset"
    python3 - "$temporary/$asset" "$BIN/zellij" <<'PY'
import os, pathlib, tarfile, sys
archive, target = sys.argv[1:]
with tarfile.open(archive, "r:gz") as package:
    members = [item for item in package.getmembers() if pathlib.PurePosixPath(item.name).name == "zellij"]
    if len(members) != 1 or not members[0].isfile():
        raise SystemExit("invalid Zellij archive")
    source = package.extractfile(members[0])
    if source is None:
        raise SystemExit("invalid Zellij archive")
    temporary = target + ".tmp"
    with open(temporary, "wb") as output:
        output.write(source.read())
    os.chmod(temporary, 0o755)
    os.replace(temporary, target)
PY
    trap - EXIT HUP INT TERM
    rm -rf "$temporary"
fi

safe_link() {
    source=$1
    target=$2
    if [ -e "$target" ] || [ -L "$target" ]; then
        if [ ! -L "$target" ]; then
            echo "Refusing to overwrite an unmanaged command: $target" >&2
            exit 1
        fi
        if ! python3 - "$source" "$target" <<'PY'
import os, pathlib, sys
source, target = map(pathlib.Path, sys.argv[1:])
try:
    if source.resolve(strict=True) != target.resolve(strict=True):
        raise SystemExit(1)
except OSError:
    raise SystemExit(1)
PY
        then
            echo "Refusing to replace a launcher owned by another program: $target" >&2
            exit 1
        fi
    fi
    ln -sfn "$source" "$target"
}

for f in "$repo"/bin/*; do
    [ -f "$f" ] && [ ! -L "$f" ] || continue
    safe_link "$f" "$BIN/$(basename "$f")"
    echo "link  $BIN/$(basename "$f")"
done

# Layouts are generated from the selected panes at runtime.
rm -f "$LAYOUTS/ai.kdl"

# SessionEnd 훅 등록 — Claude Code 와 Gemini CLI 는 같은 스키마를 쓴다.
# 기존 설정은 보존하고 hooks 키만 병합한다.
# Codex 는 세션 종료 이벤트가 없어 zellij 레이아웃에서 종료 직후 실행한다.
python3 - "$SETTINGS" "$RONDO_USER_HOME/.gemini/settings.json" <<'PY'
import json, os, shutil, sys

for path, agent in zip(sys.argv[1:], ("Claude", "Gemini")):
    entry = {"type": "command", "command": "handoff " + agent}
    cfg = {}
    existed = os.path.exists(path)
    if existed:
        try:
            with open(path) as fh:
                cfg = json.load(fh)
        except (OSError, ValueError) as error:
            print("skip  %-6s 설정 파일을 읽을 수 없음: %s" % (agent, error))
            continue

    changed = False
    hooks = cfg.setdefault("hooks", {}).setdefault("SessionEnd", [])
    if any(entry in group.get("hooks", []) for group in hooks):
        print("hook  %-6s 이미 등록됨" % agent)
    else:
        hooks.append({"hooks": [entry]})
        changed = True
        print("hook  %-6s SessionEnd 등록" % agent)

    snap = {"type": "command", "command": "rondo snap --auto"}
    prompts = cfg.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    if any(snap in group.get("hooks", []) for group in prompts):
        print("snap  %-6s 이미 등록됨" % agent)
    else:
        prompts.append({"hooks": [snap]})
        changed = True
        print("snap  %-6s UserPromptSubmit 등록" % agent)

    if agent == "Claude":
        if cfg.get("statusLine"):
            print("status Claude 기존 statusLine 유지")
        else:
            cfg["statusLine"] = {
                "type": "command",
                "command": "rondo-claude-status",
                "refreshInterval": 5,
            }
            changed = True
            print("status Claude Rondo statusLine 등록")

    if changed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if existed and not os.path.exists(path + ".bak"):
            shutil.copy(path, path + ".bak")
        temporary = path + ".rondo.tmp"
        with open(temporary, "w") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
PY

case ":$PATH:" in
    *":$BIN:"*) ;;
    *)
        case "${SHELL:-}" in
            */zsh) profile="$RONDO_USER_HOME/.zshrc" ;;
            */bash) profile="$RONDO_USER_HOME/.bashrc" ;;
            *) profile="$RONDO_USER_HOME/.profile" ;;
        esac
        touch "$profile"
        if ! grep -F "$BIN" "$profile" >/dev/null 2>&1; then
            printf '\n# Rondo\nexport PATH="%s:$PATH"\n' "$BIN" >> "$profile"
            echo "path  $profile 갱신"
        fi
        ;;
esac

echo
echo "완료. 사용법:"
echo "  rondo           첫 설정 후 프로젝트 세션 열기"
echo "  rondo setup     저장된 설정 변경"
echo "  rondo doctor    설치 상태 확인"
echo "  rondo update    새 릴리스 확인·설치"
echo "  handoff --init  이 레포에서 핸드오프 기록 켜기"
