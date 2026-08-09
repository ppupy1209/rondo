#!/bin/sh
# One-command bootstrap or local installer for macOS and Linux.
set -eu

case "$0" in
    *install.sh) ;;
    *)
        command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
        command -v tar >/dev/null 2>&1 || { echo "tar is required" >&2; exit 1; }
        app="${RONDO_INSTALL_DIR:-$HOME/.local/share/rondo}"
        archive=$(mktemp)
        trap 'rm -f "$archive"' EXIT HUP INT TERM
        mkdir -p "$app"
        curl -fsSL "https://github.com/ppupy1209/rondo/archive/refs/heads/main.tar.gz" -o "$archive"
        tar -xzf "$archive" -C "$app" --strip-components=1
        rm -f "$archive"
        trap - EXIT HUP INT TERM
        exec sh "$app/install.sh"
        ;;
esac

repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RONDO_USER_HOME="${RONDO_HOME:-$HOME}"
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
        Darwin-arm64) target=aarch64-apple-darwin ;;
        Darwin-x86_64) target=x86_64-apple-darwin ;;
        Linux-aarch64|Linux-arm64) target=aarch64-unknown-linux-musl ;;
        Linux-x86_64) target=x86_64-unknown-linux-musl ;;
        *) echo "Unsupported platform for automatic Zellij installation: $(uname -s) $(uname -m)" >&2; exit 1 ;;
    esac
    echo "install Zellij"
    curl -fsSL "https://github.com/zellij-org/zellij/releases/latest/download/zellij-$target.tar.gz" | tar -xz -C "$BIN" zellij
    chmod +x "$BIN/zellij"
fi

for f in "$repo"/bin/*; do
    ln -sfn "$f" "$BIN/$(basename "$f")"
    echo "link  $BIN/$(basename "$f")"
done

# Layouts are generated from the selected panes at runtime.
rm -f "$LAYOUTS/ai.kdl"

# SessionEnd 훅 등록 — Claude Code 와 Gemini CLI 는 같은 스키마를 쓴다.
# 기존 설정은 보존하고 hooks 키만 병합한다.
# Codex 는 세션 종료 이벤트가 없어 zellij 레이아웃에서 종료 직후 실행한다.
if command -v python3 >/dev/null 2>&1; then
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

    # Keep custom status lines. The legacy command is a compatibility alias.
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
        temp = path + ".rondo.tmp"
        with open(temp, "w") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
PY
else
    echo "hook  python3 없음 — SessionEnd 훅은 직접 등록 필요" >&2
fi

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
echo "  rondo setup     언어·패널·인계 설정"
echo "  rondo           프로젝트 세션 열기"
echo "  rondo doctor    설치 상태 확인"
echo "  handoff --init  이 레포에서 핸드오프 기록 켜기"
