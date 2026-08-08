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

# Claude Code SessionEnd 훅 등록 — 기존 설정은 보존하고 hooks 키만 병합
if command -v python3 >/dev/null 2>&1; then
    python3 - "$SETTINGS" <<'PY'
import json, os, shutil, sys

path = sys.argv[1]
entry = {"type": "command", "command": "handoff Claude"}
cfg = {}
if os.path.exists(path):
    shutil.copy(path, path + ".bak")
    with open(path) as fh:
        cfg = json.load(fh)

hooks = cfg.setdefault("hooks", {}).setdefault("SessionEnd", [])
if any(entry in group.get("hooks", []) for group in hooks):
    print("hook  이미 등록됨")
else:
    hooks.append({"hooks": [entry]})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("hook  SessionEnd 등록 (기존 파일은 .bak 로 백업)")
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
