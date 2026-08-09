# ai-tools

Claude Code · Codex · Antigravity · Kimi · Grok 를 프로젝트 단위로 함께 쓰기 위한 개인 도구.

- **`ai`** — 프로젝트마다 zellij 세션 하나. 한 화면에 AI 3개, 껐다 켜도 유지
- **`handoff`** — 세션이 끝나면 그동안의 커밋을 레포의 핸드오프 문서에 기록
- **`codex-session` · `agy-session`** — `ai` 가 패널에서 쓰는 래퍼. 직접 칠 일은 없다

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
ai              # 현재 레포 이름으로 세션 열기 / 붙기
ai 실험용        # 이름 직접 지정
ai add kimi     # 현재 세션에 AI 패널 추가
ai -l           # 열려 있는 세션 목록
```

```
┌──────────────────┬──────────────────┐
│                  │      codex       │
│      claude      ├──────────────────┤
│                  │   antigravity    │
└──────────────────┴──────────────────┘
   탭: ai | shell
```

### 패널 추가 · 삭제

```sh
ai add <claude|codex|antigravity|gemini|kimi|grok>
```

zellij 세션 안에서 실행한다(보통 `shell` 탭). 종료 후 `handoff` 까지 자동으로 이어 붙는다. 설치 안 된 CLI 는 실행 전에 걸러낸다.

삭제는 zellij 기본 키다. 따로 명령이 없다.

- `Ctrl+p` 다음 `x` — 현재 패널 닫기
- `Ctrl+p` 다음 `n` — 빈 패널 열기

### 지원 CLI

| 에이전트 | 명령 | 기본 레이아웃 | 설치 |
|---|---|---|---|
| Claude Code | `claude` | ✓ | `curl -fsSL https://claude.ai/install.sh \| bash` |
| Codex CLI | `codex` | ✓ | `npm install -g @openai/codex` |
| Antigravity CLI | `agy` | ✓ | `curl -fsSL https://antigravity.google/cli/install.sh \| bash` |
| Gemini CLI | `gemini` | | `npm install -g @google/gemini-cli` (Antigravity 의 전신) |
| Kimi Code CLI | `kimi` | | `curl -fsSL https://code.kimi.com/kimi-code/install.sh \| bash` |
| Grok Build | `grok` | | `curl -fsSL https://x.ai/cli/install.sh \| bash` |

기본 레이아웃에 3개만 두는 이유: 한 화면에 5개면 패널당 40열 남짓이라 TUI 가 깨진다. 나머지는 `ai add` 로 필요할 때만.

> **npm 이름 주의.** Kimi 와 Grok 은 npm 에 공식 패키지가 없다. `@kimi-code/cli` 는 존재하지 않고, `kimi-cli`(0.0.2) 와 `@xai-official/grok`(1.0.0) 은 저장소 URL 도 없는 별개 패키지다. [xai-org/grok-build](https://github.com/xai-org/grok-build) 는 "npm 패키지 없음(Rust 프로젝트)"이라고 명시한다. 위 표의 공식 설치 스크립트만 쓸 것.

설치 위치가 서로 다르다 — `kimi` 는 `~/.kimi-code/bin`, `grok` 은 `~/.grok/bin`. 각 설치 스크립트가 `~/.zshrc` 에 PATH 를 추가하므로 설치 후 새 터미널을 열어야 `ai add` 가 찾는다.

대상을 늘리려면 `bin/ai` 의 `agent_cmd()` 에 한 줄 추가하면 된다.

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

### AI 별 연결 방식

| CLI | 방식 | 실행 시점 |
|---|---|---|
| Claude Code | `~/.claude/settings.json` 의 `SessionEnd` 훅 | 세션 종료 |
| Gemini CLI | `~/.gemini/settings.json` 의 `SessionEnd` 훅 (Claude 와 같은 스키마) | 세션 종료 |
| Codex CLI | `codex-session` 래퍼 | codex 종료 직후 |
| Antigravity CLI | `agy-session` 래퍼 | agy 종료 직후 |
| Kimi · Grok | `ai add` 가 붙이는 래퍼 | CLI 종료 직후 |

Claude · Gemini 는 진짜 `SessionEnd` 훅이 있다. 나머지는 없거나 확인되지 않아 실행을 감싼다.

Codex 에 훅을 못 다는 이유: 훅 이벤트 목록에 **세션 종료가 없다**. `pre_tool_use` · `post_tool_use` · `session_start` · `user_prompt_submit` · `subagent_start` · `subagent_stop` · `pre_compact` · `post_compact` · `permission_request` 뿐이다. `notify` 키가 있지만 Computer Use 가 이미 쓰고 있어 건드리지 않는다.

래퍼 방식은 `ai` 로 띄운 세션에서만 돈다. CLI 를 직접 실행했다면 끝나고 한 번:

```sh
handoff Codex
```

### 기록되는 것 / 안 되는 것

커밋 메시지만 기록한다. **커밋하지 않으면 아무것도 남지 않는다.**

`## 다음 액션`, 막힌 것, 결정 근거는 사람이 쓴다. 스크립트가 건드리지 않는다.

## 제거

```sh
rm ~/.local/bin/ai ~/.local/bin/handoff ~/.local/bin/codex-session ~/.local/bin/agy-session ~/.config/zellij/layouts/ai.kdl
```

`~/.claude/settings.json` 과 `~/.gemini/settings.json` 의 `hooks.SessionEnd` 항목도 지운다. 설치 시 만들어 둔 `.bak` 이 각각 같은 위치에 있다.
