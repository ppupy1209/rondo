# ai-tools

Claude Code · Codex · Gemini 를 프로젝트 단위로 함께 쓰기 위한 개인 도구.

- **`ai`** — 프로젝트마다 zellij 세션 하나. 한 화면에 AI 3개, 껐다 켜도 유지
- **`handoff`** — 세션이 끝나면 그동안의 커밋을 레포의 핸드오프 문서에 기록

## 설치

```sh
git clone https://github.com/ppupy1209/ai-tools.git ~/ai-tools
sh ~/ai-tools/install.sh
```

필요한 것: `zellij`(`brew install zellij`), `~/.local/bin` 이 PATH 에 있을 것.

설치는 **symlink** 를 건다. 이후 업데이트는 pull 만 하면 즉시 반영된다.

```sh
git -C ~/ai-tools pull
```

`install.sh` 재실행은 파일이 새로 추가됐을 때만. 여러 번 실행해도 안전하다.

## `ai` — 프로젝트별 AI 세션

```sh
ai            # 현재 레포 이름으로 세션 열기 / 붙기
ai 실험용      # 이름 직접 지정
ai -l         # 열려 있는 세션 목록
```

```
┌──────────────────┬──────────────────┐
│                  │      codex       │
│      claude      ├──────────────────┤
│                  │      gemini      │
└──────────────────┴──────────────────┘
   탭: ai | shell
```

레포 하위 디렉터리에서 실행해도 **레포 루트 이름**으로 잡힌다. 레포가 아니면 현재 디렉터리 이름을 쓴다.

키: `Ctrl+p`+방향키 pane 이동 · `Ctrl+t`+방향키 탭 이동 · `Ctrl+o` `d` 디태치

디태치해도 세션은 살아 있다. 다른 PC 나 폰에서 SSH 로 들어와 `ai` 를 다시 치면 그대로 이어진다.

세션 정리:

```sh
zellij delete-session <이름> --force
```

## `handoff` — 작업 기록

Claude Code 세션이 끝나면(`SessionEnd` 훅) 자동 실행된다. 지난 실행 이후의 **커밋 메시지**를 핸드오프 문서의 `## 현재 단계` 맨 위에 쌓는다.

```
- 2026-08-09 · Claude — docs(web): Keyset 전환 조건 명확화
```

항목이 20개를 넘으면 오래된 것부터 `<문서와 같은 위치>/archive/` 로 옮긴다. 지우지 않는다. 그래서 다음 세션이 읽어야 할 분량이 계속 짧게 유지된다.

### 레포마다 켜기 (opt-in)

대상 문서가 없는 레포에서는 아무 일도 하지 않는다. 켜려면:

```sh
handoff --init
```

`docs/handoff.md` 가 생긴다. 대상 문서를 찾는 순서:

1. `$HANDOFF_FILE`
2. `docs/collab/status.md`
3. `docs/handoff.md`

`## 현재 단계` 헤딩이 있어야 동작한다.

### Codex · Gemini

각 CLI 는 훅 규격이 달라 자동 연결은 안 돼 있다. 직접 실행하면 누가 했는지 기록에 남는다.

```sh
handoff Codex
```

### 기록되는 것 / 안 되는 것

커밋 메시지만 기록한다. **커밋하지 않으면 아무것도 남지 않는다.**

`## 다음 액션`, 막힌 것, 결정 근거는 사람이 쓴다. 스크립트가 건드리지 않는다.

## 제거

```sh
rm ~/.local/bin/ai ~/.local/bin/handoff ~/.config/zellij/layouts/ai.kdl
```

`~/.claude/settings.json` 의 `hooks.SessionEnd` 항목도 지운다. 설치 시 만들어 둔 `.bak` 이 같은 위치에 있다.
