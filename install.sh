#!/bin/sh
# bin/ 과 zellij 레이아웃을 symlink 로 건다. symlink 라서 이후에는 git pull 만으로 반영된다.
# 새 파일이 추가됐을 때만 다시 실행하면 된다. 여러 번 실행해도 안전.
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN="$HOME/.local/bin"
LAYOUTS="$HOME/.config/zellij/layouts"
SETTINGS="$HOME/.claude/settings.json"

mkdir -p "$BIN" "$LAYOUTS"

for f in "$repo"/bin/*; do
    ln -sfn "$f" "$BIN/$(basename "$f")"
    echo "link  $BIN/$(basename "$f")"
done

ln -sfn "$repo/zellij/ai.kdl" "$LAYOUTS/ai.kdl"
echo "link  $LAYOUTS/ai.kdl"

# SessionEnd 훅 등록 — Claude Code 와 Gemini CLI 는 같은 스키마를 쓴다.
# 기존 설정은 보존하고 hooks 키만 병합한다.
# Codex 는 세션 종료 이벤트가 없어 zellij 레이아웃에서 종료 직후 실행한다.
if command -v python3 >/dev/null 2>&1; then
    python3 - "$SETTINGS" "$HOME/.gemini/settings.json" <<'PY'
import json, os, shutil, sys

for path, agent in zip(sys.argv[1:], ("Claude", "Gemini")):
    entry = {"type": "command", "command": "handoff " + agent}
    cfg = {}
    if os.path.exists(path):
        shutil.copy(path, path + ".bak")
        with open(path) as fh:
            cfg = json.load(fh)

    changed = False
    hooks = cfg.setdefault("hooks", {}).setdefault("SessionEnd", [])
    if any(entry in group.get("hooks", []) for group in hooks):
        print("hook  %-6s 이미 등록됨" % agent)
    else:
        hooks.append({"hooks": [entry]})
        changed = True
        print("hook  %-6s SessionEnd 등록" % agent)

    # 모델·컨텍스트·5시간/주간 한도 표시. 이미 statusLine 이 있으면 건드리지 않는다.
    if agent == "Claude":
        if cfg.get("statusLine"):
            print("status Claude 기존 statusLine 유지")
        else:
            cfg["statusLine"] = {"type": "command", "command": "claude-statusline"}
            changed = True
            print("status Claude statusLine 등록")

    if changed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
PY
else
    echo "hook  python3 없음 — SessionEnd 훅은 직접 등록 필요" >&2
fi

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "주의  $BIN 이 PATH 에 없음. ~/.zshrc 에 추가 필요" >&2 ;;
esac

echo
echo "완료. 사용법:"
echo "  ai              프로젝트별 AI 세션 열기"
echo "  handoff --init  이 레포에서 핸드오프 기록 켜기"
